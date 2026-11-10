import {renderAnalysisResult} from './rolling_analysis_result.js';

const $ = id => document.getElementById(id);
const ROUTE = '/api/v2/cad/analyses';
const CRB = 'rolling.cylindrical_roller';
const ACB = 'rolling.angular_contact_ball';
const SHA = /^[a-f0-9]{64}$/;
const CONDITIONS = [
  ['load_x_n', 'X 向载荷 (N)', -1e6, 1e6],
  ['load_y_n', 'Y 向载荷 (N)', -1e6, 1e6],
  ['load_z_n', 'Z 向载荷 (N)', -1e6, 1e6],
  ['outer_speed_rpm', '外圈转速 (rpm)', -1e5, 1e5],
  ['inner_speed_rpm', '内圈转速 (rpm)', -1e5, 1e5],
  ['free_clearance_mm', '分析游隙 (mm)', 0, 10],
];
const ERRORS = {
  ANALYSIS_BUSY: '求解器正处理另一项分析，请稍后重试。',
  ANALYSIS_TIMEOUT: '原版求解器超过执行时限。',
  DESIGN_HASH_MISMATCH: '设计快照与服务端哈希不一致，请重新生成三维模型。',
  ANALYSIS_EXECUTION_FAILED: '原版求解器执行失败。',
  ANALYSIS_OUTPUT_INVALID: '本次执行缺少有效输出文件。',
  ANALYSIS_RESULT_INVALID: '本次输出解析或来源绑定失败。',
  ANALYSIS_STORAGE_LIMIT: '本机运行记录已满，请由操作员归档。',
};

function option(value, label) {
  const item = document.createElement('option');
  item.value = value;
  item.textContent = label;
  return item;
}

function field(parent, key, label, input) {
  const wrapper = document.createElement('label');
  wrapper.className = 'field';
  wrapper.textContent = label;
  input.id = 'analysis-' + key;
  wrapper.append(input);
  parent.append(wrapper);
}

function numeric(value, label, min, max) {
  if (!value.trim() || !Number.isFinite(Number(value)) || Number(value) < min || Number(value) > max) {
    throw Error(label + '需填写 ' + min + ' 至 ' + max + ' 范围内的数值。');
  }
  return Number(value);
}

function compatibility(design) {
  const {bearing_type: type, parameters: p} = design;
  if (type === CRB && (p.configuration !== 'N' || p.roller_profile !== 'plain' ||
      p.roller_end_chamfer_mm !== 0 || p.roller_crown_relief_mm !== 0)) {
    return '仅支持 N 型直滚子，当前 CAD 构型或修形暂不可分析。';
  }
  if (type !== CRB && design.cage) return '当前设计包含显式 CAD 保持架，暂不可分析。';
  if (type === ACB && Object.hasOwn(p, 'cage_material')) return '当前 ACB 指定了 CAD 保持架材料，暂不可分析。';
  return '';
}

function sameFields(actual, expected) {
  return actual && Object.keys(actual).length === Object.keys(expected).length &&
    Object.entries(expected).every(([key, value]) => actual[key] === value);
}

export function initAnalysisWorkbench({getType, getDesign, getConfirmedKey, getCad}) {
  const picker = $('analysisProfile');
  const submit = $('runAnalysis');
  const allowMismatch = $('analysisAllowMismatch');
  let availability = null, refreshId = 0, busy = false, revision = 0;
  let lastResult = null, geometryType = null;
  for (const [key, label] of CONDITIONS) {
    const input = document.createElement('input');
    input.type = 'number';
    input.step = 'any';
    input.placeholder = '继承参考配置';
    field($('analysisConditions'), key, label, input);
  }

  function notice(message, error = false) {
    $('analysisStatus').textContent = message;
    $('analysisStatus').classList.toggle('error', error);
  }

  function currentDesign() {
    try { return getDesign(); } catch { return null; }
  }

  function profiles() {
    return availability?.profiles ?? {};
  }

  function syncDesign() {
    const design = currentDesign();
    const confirmed = design && getConfirmedKey() === JSON.stringify(design);
    const cad = getCad();
    const matched = confirmed && cad?.key === getConfirmedKey();
    const incompatible = design ? compatibility(design) : '';
    $('analysisDesign').textContent = incompatible || (!confirmed ? '先确认当前设计。' :
      !matched ? '当前设计已确认，等待成功生成三维模型。' :
      '设计已确认 · 三维作业 ' + cad.jobId + ' · SHA-256 ' + cad.hash);
    const profile = profiles()[picker.value];
    $('analysisProfileSource').textContent = profile ? profile.source + ' · DATA SHA-256 ' + profile.sha256 : '';
    submit.disabled = busy || !matched || Boolean(incompatible) || !availability?.available || profile?.available !== true;
    if (lastResult) {
      const historical = lastResult.revision !== revision;
      $('analysisResultVersion').textContent = historical ?
        '历史结果 · 设计或工况已改变，请按当前输入重新计算。' : '当前设计与工况的结果';
      $('analysisResultVersion').classList.toggle('is-historical', historical);
    }
  }

  function rebuildGeometry() {
    const type = getType();
    const container = $('analysisGeometry');
    container.replaceChildren();
    if (geometryType !== type) {
      for (const [key] of CONDITIONS) $('analysis-' + key).value = '';
      geometryType = type;
    }
    const p = currentDesign()?.parameters;
    if (type === CRB) {
      container.textContent = '滚子与滚道尺寸取自当前 CAD 快照。非零 CAD 径向净距时，须另行填写分析游隙。';
      return;
    }
    const diameter = document.createElement('input');
    diameter.type = 'number';
    diameter.step = 'any';
    diameter.placeholder = '按实际设计填写';
    field(container, 'inner_race_od_mm', '分析内圈外径 (mm)', diameter);
    if (type === ACB) {
      for (const [race, label] of [['inner', '内圈分析挡边'], ['outer', '外圈分析挡边']]) {
        const select = document.createElement('select');
        select.append(option('', '明确选择设计侧肩'));
        for (const [side, name] of [['left', '左肩'], ['right', '右肩']]) {
          const size = p?.[race + '_shoulder_' + side + '_d_mm'];
          if (Number.isFinite(size)) select.append(option(String(size), name + ' · ' + size + ' mm'));
        }
        field(container, race + '_sidewall_mm', label + ' (mm)', select);
      }
    }
  }

  function renderProfiles() {
    const selected = picker.value;
    picker.replaceChildren(option('', '请选择参考配置'));
    const matching = Object.entries(profiles()).filter(([, p]) => p.bearing_type === getType());
    for (const [id, profile] of matching) {
      const item = option(id, id + (profile.available ? '' : '（不可用）'));
      item.disabled = !profile.available;
      if (profile.unavailable_reason) item.title = profile.unavailable_reason;
      picker.append(item);
    }
    const available = matching.some(([, p]) => p.available);
    if (matching.some(([id, p]) => id === selected && p.available)) picker.value = selected;
    $('analysisAvailability').textContent = availability === null ? '正在检查本机分析服务…' :
      available ? '本机分析配置可用' :
      '无可用参考配置。' + (matching.find(([, p]) => p.unavailable_reason)?.[1].unavailable_reason ||
        availability.unavailable_reason || '请核对所选轴承类型和服务端配置。');
    syncDesign();
  }

  function changeInputs() {
    revision++;
    allowMismatch.checked = false;
    $('analysisMismatch').hidden = true;
    if (!busy) notice('');
    syncDesign();
  }

  async function refresh() {
    const id = ++refreshId;
    let next;
    try {
      const response = await fetch(ROUTE + '/status', {cache: 'no-store'});
      if (!response.ok) throw Error();
      const data = await response.json();
      if (id !== refreshId) return;
      next = data;
    } catch {
      if (id !== refreshId) return;
      next = {available: false, unavailable_reason: '本机分析服务无法连接。'};
    }
    const prior = profiles()[picker.value];
    availability = next;
    const updated = profiles()[picker.value];
    if (prior && (!updated?.available || updated.sha256 !== prior.sha256)) changeInputs();
    renderProfiles();
  }

  function payload(design, hash) {
    const p = design.parameters;
    const analysis_geometry = {};
    if (design.bearing_type !== CRB) {
      analysis_geometry.inner_race_od_mm = numeric($('analysis-inner_race_od_mm').value,
        '分析内圈外径 (mm)', 0.001, 1000);
      if (!(p.bore_d_mm < analysis_geometry.inner_race_od_mm && analysis_geometry.inner_race_od_mm < p.pitch_d_mm)) {
        throw Error('分析内圈外径须大于设计内径且小于节圆直径。');
      }
    }
    if (design.bearing_type === ACB) {
      for (const key of ['inner_sidewall_mm', 'outer_sidewall_mm']) {
        const selected = $('analysis-' + key).value;
        if (!selected) throw Error('请选择 ACB 内圈和外圈各自的分析挡边。');
        analysis_geometry[key] = Number(selected);
      }
    }
    const operating_conditions = {};
    for (const [key, label, low, high] of CONDITIONS) {
      const input = $('analysis-' + key);
      if (input.validity.badInput) throw Error(label + '需填写有效数值。');
      if (input.value.trim()) operating_conditions[key] = numeric(input.value, label, low, high);
    }
    if (design.bearing_type === CRB && p.radial_clearance_mm !== 0 &&
        !Object.hasOwn(operating_conditions, 'free_clearance_mm')) {
      throw Error('当前 CAD 径向净距非零，须填写独立的分析游隙。');
    }
    return {design, request_hash: hash, profile_id: picker.value, analysis_geometry,
      operating_conditions, allow_reference_geometry_mismatch: allowMismatch.checked};
  }

  $('analysisForm').addEventListener('input', event => {
    if (event.target === allowMismatch) {
      revision++;
      syncDesign();
    } else if (event.target !== picker) changeInputs();
  });
  picker.addEventListener('change', changeInputs);
  $('workspaceAnalysisTab').addEventListener('click', refresh);
  $('analysisForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (submit.disabled) return;
    const cad = getCad();
    const started = revision;
    const timeout = availability.timeout_s || 45;
    const profile = profiles()[picker.value];
    busy = true;
    syncDesign();
    notice('正在读取 CAD 设计快照并运行 RoBAS，求解时限 ' + timeout + ' 秒…');
    try {
      const body = payload(currentDesign(), cad.hash);
      const snapshot = await fetch(cad.snapshotUrl, {cache: 'no-store', signal: AbortSignal.timeout(10000)});
      if (!snapshot.ok) throw Error('CAD 设计快照无法读取，请重新生成三维模型。');
      const bytes = await snapshot.arrayBuffer();
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
        byte => byte.toString(16).padStart(2, '0')).join('');
      if (digest !== cad.hash) throw Error('CAD 设计快照 SHA-256 不一致，请重新生成三维模型。');
      body.design = JSON.parse(new TextDecoder().decode(bytes));
      if (started !== revision || getCad() !== cad) return;
      const response = await fetch(ROUTE, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body), signal: AbortSignal.timeout((timeout + 15) * 1000)});
      const reply = await response.json();
      if (!response.ok) {
        const error = reply.error ?? {};
        if (started === revision && error.field_path === '/allow_reference_geometry_mismatch') {
          $('analysisMismatch').hidden = false;
        }
        const evidence = reply.run_id ? ' · 运行编号 ' + reply.run_id : '';
        throw Error([ERRORS[error.error_code] || '分析请求失败（HTTP ' + response.status + '）',
          error.message, error.field_path].filter(Boolean).join(' · ') + evidence);
      }
      const result = reply.result;
      if (reply.request_hash !== cad.hash || reply.profile?.id !== body.profile_id ||
          reply.profile?.sha256 !== profile.sha256 || !/^[a-f0-9]{32}$/.test(reply.run_id ?? '') ||
          !sameFields(reply.analysis_geometry, body.analysis_geometry) ||
          !sameFields(reply.operating_conditions?.requested, body.operating_conditions) ||
          reply.allow_reference_geometry_mismatch !== body.allow_reference_geometry_mismatch ||
          result?.source_binding?.status !== 'HASH_VERIFIED' ||
          result?.output_status !== 'PARSED_SUPPORTED_SECTIONS' ||
          !SHA.test(reply.generated_data_sha256 ?? '') ||
          result?.files?.['DATA.txt']?.sha256 !== reply.generated_data_sha256 ||
          !SHA.test(result?.files?.['OUT.txt']?.sha256 ?? '')) {
        throw Error('分析响应与本次设计、工况或文件来源不匹配。');
      }
      renderAnalysisResult($('analysisResultBody'), reply, cad.jobId, CONDITIONS);
      lastResult = {revision: started};
      $('analysisResult').hidden = false;
      notice(started === revision ? '已取得可展示的结果段，收敛状态见下方。' : '先前请求已返回，结果归入历史。');
    } catch (error) {
      if (started === revision) notice(error.name === 'TimeoutError' ?
        '等待本机服务响应超时。请确认求解器已结束后再试。' : error.message, true);
      else notice('先前请求已结束，请按当前输入重新计算。');
    } finally {
      busy = false;
      if (started !== revision && !lastResult) notice('输入已改变，请按当前版本运行。');
      syncDesign();
    }
  });

  rebuildGeometry();
  renderProfiles();
  return {syncDesign, invalidateDesign() { changeInputs(); rebuildGeometry(); renderProfiles(); }};
}
