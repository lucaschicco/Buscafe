const { chromium } = require('playwright');
(async () => {
  const url = process.argv[2];
  const browser = await chromium.launch({ args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] });
  const ctx = await browser.newContext({ viewport: { width: 412, height: 823 } });
  const page = await ctx.newPage(); const cdp = await ctx.newCDPSession(page);
  await page.addInitScript(() => { window.__lt = []; new PerformanceObserver(l => l.getEntries().forEach(e => window.__lt.push(e.duration))).observe({ type: 'longtask' }); });
  await page.goto(url); await page.waitForSelector('.leaflet-marker-icon'); await page.waitForTimeout(3000);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await page.evaluate(() => { window.__lt = []; });
  let up = 0; page.on('request', r => { if (r.method() === 'POST' && r.url().includes('127.0.0.1')) up += (r.postDataBuffer() || []).length; });
  for (let i = 0; i < 5; i++) { await page.mouse.move(200, 400); await page.mouse.down(); await page.mouse.move(150 + i * 20, 470, { steps: 6 }); await page.mouse.up(); await page.waitForTimeout(1500); }
  const lt = await page.evaluate(() => window.__lt);
  console.log(`${url}  5 pans: long tasks=${lt.length}, total=${Math.round(lt.reduce((a, b) => a + b, 0))}ms, max=${Math.round(Math.max(0, ...lt))}ms, upload=${(up / 1048576).toFixed(1)}MB`);
  await browser.close();
})();
