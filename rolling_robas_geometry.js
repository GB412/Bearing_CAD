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


// Sources: RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs:58
//          RoBAS/Core/BallBearing/AngularContactBallBearing/ACBOptimizer.cs:CalcuBallNum
// Original RoBAS is a selection heuristic, not evidence of optimal ball count.
export function deriveRoBASBallCount(bearingType, ballDiameterMm, pitchDiameterMm,
                                     material = 'engineering_plastic') {
  if (!ROBAS_GROOVE_COEFFICIENTS[bearingType]) return null;
  const ball = Number(ballDiameterMm);
  const pitch = Number(pitchDiameterMm);
  if (ballDiameterMm === '' || pitchDiameterMm === '' ||
      !Number.isFinite(ball) || !Number.isFinite(pitch) ||
      ball <= 0 || pitch <= ball) {
    throw new RangeError('RoBAS 球数需要 0 < Dw < Dpw');
  }
  let count;
  if (bearingType === 'rolling.deep_groove_ball') {
    // Preserve C# (int)(186 / (2*asin(Dw/Dpw)*180/pi)) + 1.
    const chordAngleDegrees = 2 * Math.asin(ball / pitch) * 180 / Math.PI;
    count = Math.trunc(186 / chordAngleDegrees) + 1;
  } else {
    // The original ACBOptimizer selection is explicitly cage-material-dependent.
    if (!['engineering_plastic', 'phenolic'].includes(material)) {
      throw new RangeError('请先选择 RoBAS 角接触轴承球数计算所用的保持架材料');
    }
    const kz = material === 'engineering_plastic'
      ? (ball <= 15 ? 1.01 + 1.5 / ball : 1.11)
      : (ball <= 15 ? 1.01 + 1.9 / ball : 1.134);
    count = Math.trunc(Math.PI * pitch / (kz * ball));
  }
  if (count < 1 || count > 64 ||
      (count > 1 && pitch * Math.sin(Math.PI / count) <= ball)) {
    throw new RangeError('RoBAS 经验球数超出 CAD 预算或球体会发生干涉');
  }
  return count;
}
