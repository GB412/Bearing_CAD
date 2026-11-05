import test from 'node:test';
import assert from 'node:assert/strict';
import {deriveRoBASGrooves, deriveRoBASBallCount, ROBAS_GROOVE_COEFFICIENTS} from '../../frontend/rolling/rolling_robas_geometry.js';

test('RoBAS DGBGeometry original 0.51/0.53 groove curvature is automatic', () => {
  assert.deepEqual(deriveRoBASGrooves('rolling.deep_groove_ball', 8), {
    inner_groove_radius_mm: 4.08,
    outer_groove_radius_mm: 4.24,
  });
  assert.equal(ROBAS_GROOVE_COEFFICIENTS['rolling.deep_groove_ball'].inner, 0.51);
});

test('RoBAS ACBGeometry uses different 0.515/0.525 groove curvature', () => {
  assert.deepEqual(deriveRoBASGrooves('rolling.angular_contact_ball', 8), {
    inner_groove_radius_mm: 4.12,
    outer_groove_radius_mm: 4.2,
  });
});

test('roller bearings have no ball groove curvature', () => {
  assert.equal(deriveRoBASGrooves('rolling.cylindrical_roller', 8), null);
});

test('invalid ball diameters are rejected rather than silently guessed', () => {
  for (const x of ['', -1, 0, 'oops', Number.NaN]) {
    assert.throws(() => deriveRoBASGrooves('rolling.deep_groove_ball', x), RangeError);
  }
});

test('original DGB 186-degree chord rule selects 11 balls for Dw=8 Dpw=54', () => {
  assert.equal(deriveRoBASBallCount('rolling.deep_groove_ball', 8, 54), 11);
  assert.equal(deriveRoBASBallCount('rolling.deep_groove_ball', 10, 54) > 0, true);
});

test('original ACB coefficient depends on explicit cage material', () => {
  assert.equal(deriveRoBASBallCount('rolling.angular_contact_ball', 8, 54, 'engineering_plastic'), 17);
  assert.equal(deriveRoBASBallCount('rolling.angular_contact_ball', 8, 54, 'phenolic'), 16);
  assert.throws(() => deriveRoBASBallCount('rolling.angular_contact_ball', 8, 54, 'unknown'), RangeError);
});

test('invalid geometries and unreasonable ball counts fail instead of silent reductions', () => {
  for (const [ball, pitch] of [[0, 54], [8, 8], [100, 54], [8, 0], [0.01, 200]]) {
    assert.throws(() => deriveRoBASBallCount('rolling.deep_groove_ball', ball, pitch), RangeError);
  }
  assert.equal(deriveRoBASBallCount('rolling.cylindrical_roller', 8, 54), null);
});
