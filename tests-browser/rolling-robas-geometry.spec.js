import {test, expect} from '@playwright/test';

test('RoBAS groove dimensions are read-only and recalculate when the ball diameter changes', async ({page}) => {
  await page.goto('/rolling.html');
  const inner=page.locator('#param-inner_groove_radius_mm');
  const outer=page.locator('#param-outer_groove_radius_mm');
  await expect(inner).toHaveAttribute('readonly', '');
  await expect(outer).toHaveAttribute('readonly', '');
  await expect(inner).toHaveValue('4.08');
  await expect(outer).toHaveValue('4.24');
  await page.locator('#param-ball_d_mm').fill('10');
  await expect(inner).toHaveValue('5.1');
  await expect(outer).toHaveValue('5.3');

  await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
  await expect(inner).toHaveValue('4.12');
  await expect(outer).toHaveValue('4.2');
  await page.locator('#param-ball_d_mm').fill('10');
  await expect(inner).toHaveValue('5.15');
  await expect(outer).toHaveValue('5.25');

  await page.locator('#bearingType').selectOption('rolling.cylindrical_roller');
  await expect(page.locator('#param-inner_groove_radius_mm')).toHaveCount(0);
});
