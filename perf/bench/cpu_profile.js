const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] });
  const ctx = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 412, height: 823 } });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Network.enable'); await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await cdp.send('Profiler.enable'); await cdp.send('Profiler.setSamplingInterval', { interval: 200 });
  await cdp.send('Profiler.start');
  await page.goto(process.argv[2] || 'http://127.0.0.1:8050/', { waitUntil: 'load' });
  await page.waitForSelector('.leaflet-marker-icon', { timeout: 60000 });
  await page.waitForTimeout(500);
  const { profile } = await cdp.send('Profiler.stop');
  const dt = {}; const idx = new Map(profile.nodes.map(n => [n.id, n]));
  for (let i = 0; i < profile.samples.length; i++) { const n = idx.get(profile.samples[i]); dt[n.id] = (dt[n.id] || 0) + profile.timeDeltas[i] / 1000; }
  const byUrl = {}, byFn = {};
  for (const n of profile.nodes) {
    const t = dt[n.id] || 0; if (!t) continue;
    const u = (n.callFrame.url || '(' + n.callFrame.functionName + ')').replace('http://127.0.0.1:8050', '').replace(/\?.*/, '').slice(0, 80);
    byUrl[u] = (byUrl[u] || 0) + t;
    const f = `${n.callFrame.functionName || '(anon)'} @ ${u.split('/').pop()}:${n.callFrame.lineNumber}`;
    byFn[f] = (byFn[f] || 0) + t;
  }
  const show = (o, k) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, k).forEach(([n, t]) => console.log(String(Math.round(t)).padStart(7) + ' ms  ' + n));
  console.log('--- self time por script (CPU 4x) ---'); show(byUrl, 14);
  console.log('--- top funciones ---'); show(byFn, 22);
  await browser.close();
})();
