const { test, expect } = require('@playwright/test');

async function settle(page) {
  await page.getByRole('heading', { level: 1 }).waitFor();
  await page.evaluate(() => document.fonts.ready);
}
async function choose(page, names) {
  await page.locator('#fileInput').setInputFiles(names.map(name => ({ name, mimeType: 'text/plain', buffer: Buffer.from(`fixture: ${name}`) })));
}

test('real multi-file upload waits for cooldown, downloads match, and clear updates listing', async ({ page, request }) => {
  await request.post('/clear');
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await choose(page, ['readme-demo.txt', 'second-demo.txt']);
  await page.getByRole('button', { name: 'Upload', exact: true }).click();
  await expect(page.locator('[data-upload-status]')).toHaveText('Uploads complete.', { timeout: 10000 });
  const links = page.locator('.upload-link');
  await expect(links).toHaveCount(2);
  for (let i = 0; i < 2; i++) {
    const response = await request.get(await links.nth(i).getAttribute('href'));
    expect(response.ok()).toBeTruthy();
    expect(await response.text()).toBe(`fixture: ${i === 0 ? 'readme-demo.txt' : 'second-demo.txt'}`);
  }
  await page.getByRole('link', { name: 'Your uploads', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your uploads', exact: true })).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await page.getByRole('button', { name: 'Clear your uploads', exact: true }).click();
  await expect(page.locator('tbody')).toContainText('No uploads from your IP yet.');
  expect(errors).toEqual([]);
});

test('failed uploads stay failed and do not report success', async ({ page }) => {
  await page.route('**/upload', route => route.fulfill({ status: 413, body: 'IP quota exceeded' }));
  await page.goto('/');
  await choose(page, ['quota-test.txt']);
  await page.getByRole('button', { name: 'Upload', exact: true }).click();
  await expect(page.locator('[data-upload-status]')).toContainText('1 file(s) failed');
  await expect(page.locator('.upload-item')).toHaveClass(/is-error/);
  await expect(page.locator('.upload-link')).toHaveCount(0);
});

test('oversized file is rejected before upload; theme is keyboard accessible and persists', async ({ page }) => {
  await page.goto('/');
  await page.locator('#fileInput').setInputFiles({ name: 'oversized.bin', mimeType: 'application/octet-stream', buffer: Buffer.alloc(1024 ** 2 + 1) });
  await expect(page.locator('.upload-meta')).toHaveText(/File exceeds upload limit/);
  const theme = page.locator('[data-theme-toggle]');
  await theme.focus();
  await page.keyboard.press('Enter');
  const next = await page.locator('body').getAttribute('data-theme');
  await page.reload();
  await expect(page.locator('body')).toHaveAttribute('data-theme', next);
});

test('both themes fit five widths with empty and long-name populated states', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await request.post('/clear');
  for (const populated of [false, true]) {
    if (populated) {
      await request.post('/upload', { multipart: { file: { name: `project-${'long-name-'.repeat(14)}.txt`, mimeType: 'text/plain', buffer: Buffer.from('fixture') } } });
    }
    for (const width of [320, 390, 768, 1024, 1440]) {
      for (const theme of ['light', 'dark']) {
        await page.setViewportSize({ width, height: 1000 });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        for (const route of ['/', '/uploads']) {
          await page.goto(route);
          await settle(page);
          if (route === '/' && populated) await choose(page, [`${'very-long-'.repeat(20)}.txt`]);
          const geometry = await page.evaluate(() => ({
            page: document.documentElement.scrollWidth - innerWidth,
            main: document.body.scrollWidth - document.body.clientWidth,
            cards: [...document.querySelectorAll('.upload-panel,.section-card')].map(x => x.scrollWidth - x.clientWidth),
          }));
          expect(geometry.page, `${route} ${theme} ${width}`).toBeLessThanOrEqual(1);
          expect(geometry.main).toBeLessThanOrEqual(1);
          expect(geometry.cards.every(value => value <= 1)).toBeTruthy();
        }
      }
    }
  }
  expect(errors).toEqual([]);
});
