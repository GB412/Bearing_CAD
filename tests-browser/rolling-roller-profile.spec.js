import {test, expect} from '@playwright/test';

test('CRB roller detail mode controls optional crown and chamfer inputs', async ({page}) => {
  await page.goto('/rolling.html');
  await page.locator('#bearingType').selectOption('rolling.cylindrical_roller');
  await expect(page.locator('#param-roller_profile')).toHaveValue('crowned');
  await expect(page.locator('#param-roller_end_chamfer_mm')).toHaveValue('0.2');
  await expect(page.locator('#param-roller_crown_relief_mm')).toHaveValue('0.02');
  await page.locator('#param-roller_profile').selectOption('plain');
  await expect(page.locator('#param-roller_end_chamfer_mm')).toHaveValue('0');
  await expect(page.locator('#param-roller_crown_relief_mm')).toHaveValue('0');
  await expect(page.locator('#param-roller_end_chamfer_mm')).toHaveAttribute('readonly', '');
  await page.locator('#param-roller_profile').selectOption('chamfered');
  await expect(page.locator('#param-roller_end_chamfer_mm')).toHaveValue('0.2');
  await expect(page.locator('#param-roller_crown_relief_mm')).toHaveValue('0');
  await page.locator('#param-roller_profile').selectOption('crowned');
  await expect(page.locator('#param-roller_crown_relief_mm')).toHaveValue('0.02');
});
