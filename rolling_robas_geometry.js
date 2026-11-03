// Original RoBAS design-entry groove curvature defaults, distinct from full optimization.
// Sources: RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs:60-61
//          RoBAS/Core/BallBearing/AngularContactBallBearing/ACBGeometry.cs:57-58
// All dimensions passed to the web workbench are millimetres.
// The RoBAS static optimizer also uses 0.51/0.53 for DGB; different scalar
// constructors contain other defaults, so do not silently combine paths.
export const ROBAS_GROOVE_COEFFICIENTS = Object.freeze({
  'rolling.deep_groove_ball': Object.freeze({inner: 0.51, outer: 0.53}),
  'rolling.angular_contact_ball': Object.freeze({inner: 0.515, outer: 0.525}),
});

export function deriveRoBASGrooves(bearingType, ballDiameterMm) {
  const coefficients = ROBAS_GROOVE_COEFFICIENTS[bearingType];
  if (!coefficients) return null;
  const d = Number(ballDiameterMm);
  if (ballDiameterMm === '' || ballDiameterMm === null || !Number.isFinite(d) || d <= 0) {
    throw new RangeError('钢球直径必须为正的毫米尺寸');
  }
  const round = value => Number(value.toPrecision(12));
  return {
    inner_groove_radius_mm: round(d * coefficients.inner),
    outer_groove_radius_mm: round(d * coefficients.outer),
  };
}
