import { test, expect } from '@playwright/test';

test('loads bundled demo and updates 2D preview offline', async ({ page, context }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await context.setOffline(true);
  await expect(page).toHaveTitle(/BearingCAD Studio/);
  await expect(page.locator('#visual2d')).toContainText('轴颈');
  await expect(page.locator('#stage canvas')).toHaveCount(1);
  await page.locator('#shaft_d_mm').fill('60');
  await page.locator('#bush_od_mm').fill('82');
  await page.locator('#housing_od_mm').fill('100');
  await expect(page.locator('#visual2d')).toContainText('60');
  await expect(page.locator('#visual2d')).toContainText('82');
  await expect(page.locator('#visual2d')).toContainText('100');
  await expect(page.locator('#saveDxf')).toBeEnabled();
  expect(errors).toEqual([]);
});

test('invalid shared parameters clear views and block exports', async ({ page }) => {
  await page.goto('/');
  await page.locator('#bush_od_mm').fill('50');
  await expect(page.locator('#previewInvalid')).toBeVisible();
  await expect(page.locator('#visual2d')).toHaveText('');
  await expect(page.locator('#saveSvg')).toBeDisabled();
  await expect(page.locator('#saveDxf')).toBeDisabled();
  await expect(page.locator('#saveJson')).toBeDisabled();
  await page.locator('#bush_od_mm').fill('70');
  await expect(page.locator('#previewInvalid')).toBeHidden();
  await expect(page.locator('#visual2d')).toContainText('轴颈');
});

test('view controls and fixed STEP asset are usable', async ({ page }) => {
  await page.goto('/');
  await page.locator('#showHousing').uncheck();
  await expect(page.locator('#showHousing')).not.toBeChecked();
  await page.locator('#transparent').check();
  await page.locator('#explode').fill('90');
  await expect(page.locator('#explode')).toHaveValue('90');
  const response = await page.request.get('/outputs/bearing_assembly.step');
  expect(response.ok()).toBeTruthy();
  expect((await response.body()).length).toBeGreaterThan(1000);
});
