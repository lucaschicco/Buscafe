const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] });
  const page = await (await browser.newContext({ viewport: { width: 412, height: 823 }, deviceScaleFactor: 3, isMobile: true })).newPage();
  const tiles = []; page.on('request', r => { if (/basemaps/.test(r.url())) tiles.push(r.url().replace(/https:\/\/.\.basemaps\.cartocdn\.com\/light_all\//, '').replace(/\?key=.*/, '')); });
  await page.goto('http://127.0.0.1:8050/'); await page.waitForSelector('.leaflet-marker-icon'); await page.waitForTimeout(3000);
  const ret = tiles.filter(t => t.includes('@2x')).length;
  console.log(`tile requests: ${tiles.length} (normales=${tiles.length - ret}, @2x=${ret})`); console.log(tiles.slice(0, 3), tiles.filter(t => t.includes('@2x')).slice(0, 2));
  await browser.close();
})();
