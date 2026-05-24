
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 2200 } });
  const errors = [];
  page.on('pageerror', err => errors.push(`pageerror: ${err.message}`));
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(`console: ${msg.text()}`);
  });
  await page.goto('http://127.0.0.1:8000/index.html', { waitUntil: 'networkidle' });
  await page.waitForTimeout(5000);
  const titleVisible = await page.locator('.inner-title').isVisible();
  await page.screenshot({ path: 'output/playwright/scalient-offline-full.png', fullPage: true });
  console.log(JSON.stringify({ titleVisible, errors }, null, 2));
  await browser.close();
})();
