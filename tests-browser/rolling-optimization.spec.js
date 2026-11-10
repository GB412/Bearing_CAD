import {test, expect} from '@playwright/test';

const optimized = {
  schema_version: 'bearing-cad.robas-dgb-optimization.v1',
  candidate_only: true, applied: false,
  source_model: '6008', source_initial_hash: 'a'.repeat(64),
  total_valid_candidates: 7,
  candidates: [{
    rank: 1, candidate_id: 'dgb-opt-01', score: .92,
    metrics: {
      dynamic_load_n: 19000, static_load_n: 14000,
      radial_stiffness_source_units: 197000,
      fill_angle_deg: 193.8,
    },
    design: {
      schema_version: 'bearing-cad.request.v1',
      bearing_type: 'rolling.deep_groove_ball',
      unit: 'mm', detail_level: 'functional', geometry_strategy: 'explicit',
      parameters: {
        bore_d_mm: 40, outside_d_mm: 68, width_mm: 15,
        ball_d_mm: 8.5, pitch_d_mm: 55.5, ball_count: 12,
        inner_groove_radius_mm: 4.335, outer_groove_radius_mm: 4.505,
        inner_shoulder_d_mm: 49.975, outer_shoulder_d_mm: 61.038,
      },
      cage: {
        kind: 'simplified_annular', inner_d_mm: 50.9745,
        outside_d_mm: 59.81724, width_mm: 14.25,
        pocket_clearance_mm: .25,
      },
    },
  }],
};

async function setup(page, observed) {
  await page.route('**/api/v2/cad/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v2/cad/status') {
      return route.fulfill({json: {
        available: true, robas_sizing_available: true,
        robas_optimization_available: true,
        supported_bearings: ['rolling.deep_groove_ball'],
      }});
    }
    if (path === '/api/v2/cad/drawings/status') {
      return route.fulfill({json: {
        available: true, supported_bearings: ['rolling.deep_groove_ball'],
      }});
    }
    if (path === '/api/v2/cad/optimization/dgb') {
      observed.initial = request.postDataJSON();
      return route.fulfill({json: optimized});
    }
    if (path === '/api/v2/cad/jobs') {
      observed.cad = request.postDataJSON();
      return route.fulfill({status: 422, json: {
        error: {error_code: 'TEST_STOP', field_path: '',
                message: 'Test stops before actual OCCT generation'},
      }});
    }
    if (path === '/api/v2/cad/drawings') {
      observed.drawing = request.postDataJSON();
      return route.fulfill({status: 422, json: {
        error: {error_code: 'TEST_STOP', message: 'Test stops before actual CADImport'},
      }});
    }
    return route.fulfill({status: 404, json: {error: {message: 'not found'}}});
  });
  await page.goto('/rolling.html');
  await page.locator('#workspace2dTab').click();
  await page.locator('#drawingClearance').selectOption('C0');
  await page.locator('#workspace3dTab').click();
  await expect(page.locator('#runRoBASOptimizer')).toBeEnabled();
}

test('DGB search uses minimal initial input and never writes CAD until candidate confirmation', async ({page}) => {
  const observed = {};
  await setup(page, observed);
  const initialBall = await page.locator('#param-ball_d_mm').inputValue();
  const initialPitch = await page.locator('#param-pitch_d_mm').inputValue();
  await page.locator('#runRoBASOptimizer').click();
  await expect(page.locator('#optimizationCandidates .optimization-candidate')).toHaveCount(1);
  expect(observed.initial.initial).toEqual({
    bearing_type: 'rolling.deep_groove_ball',
    bore_d_mm: 40, outside_d_mm: 68, width_mm: 15,
    cage: {kind: 'simplified_annular', pocket_clearance_mm: .25},
  });
  expect(observed.initial.optimization.weights).toEqual({
    dynamic_load: .8, radial_stiffness: .2,
  });
  expect(observed.initial.optimization.model).toBe('6008');
  expect(observed.initial.optimization.radial_clearance_group).toBe('C0');
  await expect(page.locator('#param-ball_d_mm')).toHaveValue(initialBall);
  await expect(page.locator('#param-pitch_d_mm')).toHaveValue(initialPitch);
  expect(observed.cad).toBeUndefined();
  expect(observed.drawing).toBeUndefined();

  await page.getByRole('button', {name: '确认并应用此设计'}).click();
  await expect(page.locator('#designConfirmation')).toContainText('当前设计已确认');
  await expect(page.locator('#param-ball_d_mm')).toHaveValue('8.5');
  await expect(page.locator('#param-pitch_d_mm')).toHaveValue('55.5');
  await expect(page.locator('#param-ball_count')).toHaveValue('12');
  await expect(page.locator('#param-inner_groove_radius_mm')).toHaveValue('4.335');
  await expect(page.locator('#param-outer_shoulder_d_mm')).toHaveValue('61.038');
  await expect(page.locator('#cage-width_mm')).toHaveValue('14.25');
  await expect(page.locator('#optimizationResults')).toBeHidden();

  await page.locator('#generate').click();
  await expect.poll(() => observed.cad?.parameters?.ball_count).toBe(12);
  expect(observed.cad.parameters.pitch_d_mm).toBe(55.5);
  await page.locator('#workspace2dTab').click();
  await page.locator('#generate2d').click();
  await expect.poll(() => observed.drawing?.design?.parameters?.ball_count).toBe(12);
  expect(observed.drawing.design.parameters.pitch_d_mm).toBe(55.5);
});

test('stale candidate suggestions are invalidated when design weights change', async ({page}) => {
  const observed = {};
  await setup(page, observed);
  await page.locator('#runRoBASOptimizer').click();
  await expect(page.locator('#optimizationResults')).toBeVisible();
  await page.locator('#optimizerCrWeight').fill('0.9');
  await expect(page.locator('#optimizationResults')).toBeHidden();
  await expect(page.locator('#param-ball_d_mm')).toHaveValue('8');
});

test('optimizer rejects missing source clearance instead of assuming C0', async ({page}) => {
  const observed = {};
  await setup(page, observed);
  await page.locator('#workspace2dTab').click();
  await page.locator('#drawingClearance').selectOption('');
  await page.locator('#workspace3dTab').click();
  await page.locator('#runRoBASOptimizer').click();
  await expect(page.locator('#status')).toContainText('选择径向游隙组');
  expect(observed.initial).toBeUndefined();
});
