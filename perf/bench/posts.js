const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'] });
  const page = await (await browser.newContext({ viewport: { width: 412, height: 823 } })).newPage();
  const t0 = Date.now();
  page.on('request', r => { if (r.method() === 'POST') { const b = r.postDataBuffer(); let out = ''; try { out = JSON.parse(b).output } catch (e) {} console.log(`${Date.now() - t0}ms POST ${r.url().replace('http://127.0.0.1:8050', '')} ${(b ? b.length / 1024 : 0).toFixed(0)}KB  output=${out}`); } });
  await page.goto('http://127.0.0.1:8050/', { waitUntil: 'load' });
  await page.waitForSelector('.leaflet-marker-icon');
  await page.waitForTimeout(2000);
  console.log('--- pan del mapa x3 ---');
  for (let i = 0; i < 3; i++) { await page.mouse.move(200, 400); await page.mouse.down(); await page.mouse.move(260, 450, { steps: 5 }); await page.mouse.up(); await page.waitForTimeout(800); }
  console.log('--- zoom in x2 ---');
  for (let i = 0; i < 2; i++) { await page.mouse.dblclick(206, 420); await page.waitForTimeout(1200); }
  await browser.close();
})();
