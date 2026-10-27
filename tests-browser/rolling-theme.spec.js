import {test,expect} from '@playwright/test';

// Visual-system contract: no screenshot-based pixel lock or API stubs needed.
test('rolling workbench uses a restrained light palette and matching part legend',async({page})=>{
 await page.goto('/rolling.html');
 await expect(page.locator('.brand')).toBeVisible();
 await expect(page.locator('.material-legend .legend-item')).toHaveCount(6);
 const values=await page.evaluate(()=>{
  const root=document.documentElement;
  const bg=getComputedStyle(document.body).backgroundColor;
  const style=getComputedStyle(root);
  const swatches=[...document.querySelectorAll('.material-legend .swatch')]
   .map(node=>getComputedStyle(node).backgroundColor);
  const viewport=getComputedStyle(document.querySelector('.stage'));
  const input=getComputedStyle(document.querySelector('#bearingType'));
  return {bg,swatches,viewportBg:viewport.backgroundColor,
    viewportGrid:viewport.backgroundImage,
    text:style.getPropertyValue('--text').trim(),
    inputBg:input.backgroundColor};
 });
 expect(values.bg).toBe('rgb(243, 245, 246)');
 expect(values.viewportBg).toBe('rgb(240, 243, 244)');
 expect(values.viewportGrid).toContain('linear-gradient');
 expect(values.inputBg).toBe('rgb(255, 255, 255)');
 expect(values.text).toBe('#24313b');
 expect(new Set(values.swatches).size).toBe(6);
});

test('parameter editor and viewer remain usable at narrow widths',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/rolling.html');
 await expect(page.locator('#bearingType')).toBeVisible();
 await expect(page.locator('#cageKind')).toBeVisible();
 await expect(page.locator('#viewport')).toBeVisible();
 const dimensions=await page.evaluate(()=>({
  scroll:document.documentElement.scrollWidth,
  viewport:document.documentElement.clientWidth,
  viewer:document.querySelector('#viewport').getBoundingClientRect().width,
  param:document.querySelector('#parameters').getBoundingClientRect().width
 }));
 expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.viewport+1);
 expect(dimensions.viewer).toBeGreaterThan(300);
 expect(dimensions.param).toBeGreaterThan(290);
});
