const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: '.', testMatch: '*.spec.js', workers: 1,
  use: { baseURL: 'http://127.0.0.1:54002', browserName: 'chromium' },
  webServer: {
    command: `${process.env.PYTHON || '../../.venv/bin/python'} serve.py`,
    url: 'http://127.0.0.1:54002/robots.txt', reuseExistingServer: false,
  },
});
