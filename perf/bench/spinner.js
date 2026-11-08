const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] });
  const ctx = await browser.newContext({ viewport: { width: 412, height: 823 } });
  const page = await ctx.newPage(); const cdp = await ctx.newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 });
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  const t0 = Date.now();
  await page.goto(process.argv[2] || 'http://127.0.0.1:8050/');
  await page.waitForSelector('.leaflet-marker-icon', { timeout: 120000 }); console.log('first marker', Date.now() - t0, 'ms');
  const vis = await page.evaluate(() => { const d = document.getElementById('loading-div'); const s = getComputedStyle(d); return { display: s.display, bg: s.backgroundColor, z: s.zIndex, w: d.offsetWidth, h: d.offsetHeight }; });
  console.log('loading-div while markers exist:', JSON.stringify(vis));
  await page.waitForFunction(() => getComputedStyle(document.getElementById('loading-div')).display === 'none', null, { timeout: 180000 });
  console.log('spinner hidden', Date.now() - t0, 'ms');
  await browser.close();
})();
