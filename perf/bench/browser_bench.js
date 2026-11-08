// Mide la carga de la home en Chromium. Uso: node browser_bench.js <perfil> <runs> [url]
// perfil: mobile (Slow 4G + CPU 4x) | desktop (sin throttling)
const { chromium } = require('playwright');
const fs = require('fs');

const PROFILE = process.argv[2] || 'mobile';
const RUNS = parseInt(process.argv[3] || '3', 10);
const URL = process.argv[4] || 'http://127.0.0.1:8050/';
const ROOT = require('path').resolve(__dirname, '..', '..', 'assets') + '/';
const TILE = fs.readFileSync(ROOT + 'icono_mapa.png');
const MARK = fs.readFileSync(ROOT + 'markverde.svg');

const NET = {
  mobile: { offline: false, latency: 150, downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 },
  desktop: null,
};
const CPU = { mobile: 4, desktop: 1 };

async function stubExternal(route) {
  const u = route.request().url();
  if (u.startsWith('http://127.0.0.1')) return route.continue();
  await new Promise(r => setTimeout(r, 80)); // ~RTT a un CDN
  if (/basemaps|tile\.openstreetmap/.test(u)) return route.fulfill({ body: TILE, contentType: 'image/png' });
  if (/\.svg/.test(u)) return route.fulfill({ body: MARK, contentType: 'image/svg+xml' });
  return route.abort(); // firebase, app insights, google fonts
}

async function run(browser, context, warm) {
  const page = await context.newPage();
  if (PROFILE === 'mobile') {
    await page.setViewportSize({ width: 412, height: 823 });
  }
  const cdp = await context.newCDPSession(page);
  await cdp.send('Network.enable');
  if (!warm) await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  if (NET[PROFILE]) await cdp.send('Network.emulateNetworkConditions', NET[PROFILE]);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: CPU[PROFILE] });

  const reqs = new Map();
  cdp.on('Network.responseReceived', e => {
    reqs.set(e.requestId, { url: e.response.url, type: e.type, status: e.response.status, fromCache: e.response.fromDiskCache || e.response.fromServiceWorker });
  });
  cdp.on('Network.loadingFinished', e => { const r = reqs.get(e.requestId); if (r) r.bytes = e.encodedDataLength; });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 140)); });
  page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 140)));

  await page.addInitScript(() => {
    window.__perf = { longTasks: [], lcp: 0 };
    new PerformanceObserver(l => l.getEntries().forEach(e => window.__perf.longTasks.push([e.startTime, e.duration]))).observe({ type: 'longtask', buffered: true });
    new PerformanceObserver(l => { const es = l.getEntries(); window.__perf.lcp = es[es.length - 1].startTime; window.__perf.lcpEl = es[es.length - 1].element && es[es.length - 1].element.tagName; }).observe({ type: 'largest-contentful-paint', buffered: true });
    const t0 = performance.now();
    const check = () => {
      if (!window.__perf.firstMarker && document.querySelector('.leaflet-marker-icon')) window.__perf.firstMarker = performance.now();
      const ld = document.getElementById('loading-div');
      if (!window.__perf.spinnerHidden && window.__perf.firstMarker && ld && getComputedStyle(ld).display === 'none') window.__perf.spinnerHidden = performance.now();
      if (!window.__perf.dashReady && document.querySelector('#map .leaflet-container, .leaflet-container')) window.__perf.dashReady = performance.now();
      if (!(window.__perf.firstMarker && window.__perf.spinnerHidden)) requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  });

  const t = Date.now();
  await page.goto(URL, { waitUntil: 'load', timeout: 120000 });
  await page.waitForFunction(() => window.__perf.firstMarker, null, { timeout: 120000 });
  await page.waitForTimeout(2500); // dejar correr el debounce / timers (initFirebase a 1.5s)
  const wall = Date.now() - t;

  const m = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0];
    const fcp = performance.getEntriesByName('first-contentful-paint')[0];
    const lt = window.__perf.longTasks;
    const fcpT = fcp ? fcp.startTime : 0;
    return {
      ttfb: nav.responseStart, htmlDone: nav.responseEnd, dcl: nav.domContentLoadedEventEnd, load: nav.loadEventEnd,
      fcp: fcpT, lcp: window.__perf.lcp, lcpEl: window.__perf.lcpEl,
      mapContainer: window.__perf.dashReady, firstMarker: window.__perf.firstMarker, spinnerHidden: window.__perf.spinnerHidden,
      longTasks: lt.length, longTaskMs: lt.reduce((a, [, d]) => a + d, 0),
      tbt: lt.filter(([s]) => s > fcpT).reduce((a, [, d]) => a + Math.max(0, d - 50), 0),
      maxLongTask: lt.reduce((a, [, d]) => Math.max(a, d), 0),
      markers: document.querySelectorAll('.leaflet-marker-icon').length,
      domNodes: document.getElementsByTagName('*').length,
      jsHeapMB: performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null,
    };
  });
  const list = [...reqs.values()];
  const local = list.filter(r => r.url.startsWith('http://127.0.0.1'));
  const by = {};
  for (const r of local) { const k = r.type; by[k] = by[k] || { n: 0, kb: 0 }; by[k].n++; by[k].kb += (r.bytes || 0) / 1024; }
  m.requests = list.length; m.localKB = local.reduce((a, r) => a + (r.bytes || 0), 0) / 1024; m.byType = by;
  m.notFound = list.filter(r => r.status >= 400).map(r => r.status + ' ' + r.url.replace('http://127.0.0.1:8050', ''));
  m.top = local.sort((a, b) => (b.bytes || 0) - (a.bytes || 0)).slice(0, 6).map(r => `${((r.bytes || 0) / 1024).toFixed(0)}KB ${r.url.replace('http://127.0.0.1:8050', '').slice(0, 70)}`);
  m.errors = errors.slice(0, 5); m.wall = wall;
  await page.close();
  return m;
}

(async () => {
  const browser = await chromium.launch({ args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] });
  const out = { cold: [], warm: [] };
  for (let i = 0; i < RUNS; i++) {
    const ctx = await browser.newContext({ serviceWorkers: 'block' });
    out.cold.push(await run(browser, ctx, false));
    out.warm.push(await run(browser, ctx, true)); // segunda visita, misma caché
    await ctx.close();
  }
  await browser.close();
  const med = (arr, k) => { const v = arr.map(x => x[k]).filter(x => typeof x === 'number').sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : null; };
  const keys = ['ttfb', 'htmlDone', 'fcp', 'lcp', 'dcl', 'load', 'mapContainer', 'firstMarker', 'spinnerHidden', 'longTasks', 'longTaskMs', 'tbt', 'maxLongTask', 'markers', 'domNodes', 'requests', 'localKB', 'jsHeapMB'];
  console.log(`\n== ${PROFILE} — mediana de ${RUNS} corridas (ms salvo indicación) ==`);
  console.log('metric'.padEnd(16), 'cold'.padStart(10), 'warm'.padStart(10));
  for (const k of keys) console.log(k.padEnd(16), String(Math.round(med(out.cold, k) ?? -1)).padStart(10), String(Math.round(med(out.warm, k) ?? -1)).padStart(10));
  console.log('LCP element:', out.cold[0].lcpEl);
  console.log('bytes by type (cold):', JSON.stringify(Object.fromEntries(Object.entries(out.cold[0].byType).map(([k, v]) => [k, `${v.n} req / ${v.kb.toFixed(0)}KB`]))));
  console.log('bytes by type (warm):', JSON.stringify(Object.fromEntries(Object.entries(out.warm[0].byType).map(([k, v]) => [k, `${v.n} req / ${v.kb.toFixed(0)}KB`]))));
  console.log('top (cold):\n  ' + out.cold[0].top.join('\n  '));
  console.log('4xx/5xx:', out.cold[0].notFound);
  console.log('console errors:', out.cold[0].errors);
  fs.writeFileSync(`${__dirname}/result_${PROFILE}_${process.env.TAG || 'base'}.json`, JSON.stringify(out, null, 1));
})();
