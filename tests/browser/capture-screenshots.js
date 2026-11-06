// Start baseline and current services first; see docs/ui-review/README.md.
const { chromium } = require('@playwright/test');
const path = require('node:path');
const output = path.resolve(__dirname, '../../docs/ui-review');
(async () => {
  const browser = await chromium.launch();
  for (const [version, base] of [['before', process.env.BASELINE_URL || 'http://127.0.0.1:54000'], ['after', process.env.CURRENT_URL || 'http://127.0.0.1:54001']]) {
    for (const theme of ['light', 'dark']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, colorScheme: theme });
      await context.addInitScript(theme => localStorage.setItem('theme', theme), theme);
      const page = await context.newPage();
      for (const route of ['/', '/uploads']) {
        await page.setViewportSize({ width: 1440, height: route === '/' ? 1100 : 600 });
        await page.goto(base + route);
        await page.getByRole('heading', { level: 1 }).waitFor();
        await page.evaluate(() => document.fonts.ready);
        if (route === '/') {
          await page.locator('#fileInput').setInputFiles([
            { name: 'project-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('demo notes') },
            { name: 'design-assets.tar.gz', mimeType: 'application/gzip', buffer: Buffer.from('demo archive') },
          ]);
        }
        await page.screenshot({ path: path.join(output, `${version}-${route === '/' ? 'home' : 'uploads'}-${theme}.png`), fullPage: true, animations: 'disabled' });
      }
      if (theme === 'light') {
        await page.setViewportSize({ width: 390, height: 1000 });
        await page.goto(base + '/');
        await page.getByRole('heading', { level: 1 }).waitFor();
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: path.join(output, `${version}-home-mobile.png`), fullPage: true, animations: 'disabled' });
      }
      await context.close();
    }
  }
  await browser.close();
})();
