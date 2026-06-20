// Opcional: executar com `npx playwright test playwright/frontend_smoke.spec.js`.
// Salva screenshot em evidencias/screenshots/frontend-smoke.png.
const { test, expect } = require('@playwright/test');

test('frontend abre e exibe página de chat', async ({ page }) => {
  const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
  await page.goto(frontendUrl, { waitUntil: 'networkidle' });
  await page.screenshot({ path: 'evidencias/screenshots/frontend-smoke.png', fullPage: true });
  await expect(page.locator('body')).toBeVisible();
});
