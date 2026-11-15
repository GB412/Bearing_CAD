const CONTACTS = [
  ['load', '接触载荷', 'N'], ['stress', '接触应力', 'MPa'],
  ['deflection', '接触变形', 'mm'], ['angle', '接触角', '°'],
  ['spin_roll_ratio', '旋滚比', '1'], ['film_thickness', '油膜厚度', 'μm'],
  ['film_temperature', '油膜温度', '°C'], ['rolling_velocity', '滚动速度', 'm/s'],
  ['major_half_width', '接触长半宽', 'm'], ['minor_half_width', '接触短半宽', 'm'],
  ['max_slip_velocity', '最大滑动速度', 'm/s'], ['traction_coefficient', '牵引系数', '1'],
  ['contact_loss', '接触功率损失', 'W'], ['contact_temperature_rise', '接触温升', 'K'],
  ['contact_temperature', '接触温度', '°C'], ['isothermal_film_thickness', '等温油膜厚度', 'μm'],
  ['film_reduction_factor', '油膜折减系数', '1'], ['max_stress_slip', '最大应力与滑速乘积', 'Pa·m/s'],
  ['max_stress_slip_position', '最大应力滑速乘积的归一化位置', '1'],
  ['load_slip_integral', '载荷与滑速积分', 'W'],
  ['outer_contact_edge_depth', '外接触边缘距肩部深度', 'm'],
  ['inner_contact_edge_chord', '内接触边缘弦距', 'm'],
  ['race_flexing', '套圈挠曲', 'm'],
];
const ELEMENTS = [
  ['spin_speed', '自转速度', 'rpm'], ['orbit_speed', '公转速度', 'rpm'],
  ['centrifugal_force', '离心力', 'N'], ['orbital_position', '周向位置', '°'],
  ['axial_position', '轴向位置', 'm'], ['relative_orbital_position', '相对公转位置', 'rad'],
  ['misalignment', '倾斜角 Mis', '°'], ['skew', '偏斜角 Skew', '°'],
  ['spin_theta', '自转方向角 Theta', '°'], ['spin_phi', '自转方向角 Phi', '°'],
  ['moving_radial_force', '运动坐标系径向力', 'N'], ['moving_orbital_force', '运动坐标系周向力', 'N'],
  ['moving_axial_force', '运动坐标系轴向力', 'N'], ['wear_rate', '时间平均磨损率', 'm³/s'],
  ['bulk_temperature', '滚动体体温', 'K'], ['bulk_convection_htc', '体对流换热系数', 'W/(m²·K)'],
];
const SWEEP = [
  ['outer_speed', '外圈转速 (rpm)'], ['inner_speed', '内圈转速 (rpm)'],
  ['displacement_x', 'X 位移 (m)'], ['displacement_y', 'Y 位移 (m)'], ['displacement_z', 'Z 位移 (m)'],
  ['stiffness_xx', 'Kxx (N/m)'], ['stiffness_yy', 'Kyy (N/m)'], ['stiffness_zz', 'Kzz (N/m)'],
];
const COLORS = ['#2479b0', '#c05e29', '#5960b2'];
const valid = metric => metric?.status === 'VALID' && Number.isFinite(metric.value);
const number = value => String(Number(value.toPrecision(8)));
const metricText = metric => valid(metric) ? number(metric.value) :
  metric?.status === 'NOT_REPORTED' ? '未报告' : '不可用' + (metric?.raw ? ' (' + metric.raw + ')' : '');

function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function table(headers, rows) {
  const wrapper = element('div');
  wrapper.className = 'analysis-table';
  const grid = element('table');
  const header = grid.createTHead().insertRow();
  for (const label of headers) {
    const cell = element('th', label);
    cell.scope = 'col';
    header.append(cell);
  }
  const body = grid.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const text of row) tr.insertCell().textContent = text;
  }
  wrapper.append(grid);
  return wrapper;
}

function svgElement(tag, attributes) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function chart(series, xLabel, yLabel) {
  const box = element('div');
  const points = series.flatMap(({points}) => points.filter(Boolean));
  if (!points.length) {
    box.append(element('p', '当前曲线没有有效数据。'));
    return box;
  }
  let [xmin, ymin] = points[0], xmax = xmin, ymax = ymin;
  for (const [px, py] of points) {
    xmin = Math.min(xmin, px); xmax = Math.max(xmax, px);
    ymin = Math.min(ymin, py); ymax = Math.max(ymax, py);
  }
  const x = v => xmin === xmax ? 351 : 80 + 542 * (v - xmin) / (xmax - xmin);
  const y = v => ymin === ymax ? 96 : 164 - 136 * (v - ymin) / (ymax - ymin);
  const svg = svgElement('svg', {viewBox: '0 0 650 212', role: 'img', 'aria-label': yLabel + ' / ' + xLabel});
  for (const [tx, ty, text, anchor] of [[75,32,number(ymax),'end'], [75,ymin === ymax ? 96 : 164,number(ymin),'end'],
    [80,184,number(xmin),'middle'], [622,184,number(xmax),'middle'], [351,204,xLabel,'middle'], [80,16,yLabel,'start']]) {
    const label = svgElement('text', {x:tx, y:ty, 'text-anchor':anchor, fill:'currentColor'});
    label.textContent = text;
    svg.append(label);
  }
  svg.append(svgElement('path', {d:'M80 26V164H622', stroke:'currentColor', fill:'none'}));
  const legend = element('p');
  legend.className = 'analysis-legend';
  series.forEach(({label, points}, index) => {
    const color = COLORS[index];
    const path = points.map((point, i) => point ? (points[i - 1] ? 'L' : 'M') + x(point[0]) + ' ' + y(point[1]) : '').join(' ');
    svg.append(svgElement('path', {d:path, fill:'none', stroke:color, 'stroke-width':2}));
    for (const point of points.filter(Boolean)) {
      const [vx, vy] = point;
      const dot = svgElement('circle', {cx:x(vx), cy:y(vy), r:3.5, fill:color});
      const title = svgElement('title', {});
      title.textContent = label + ' · ' + number(vx) + ' / ' + number(vy);
      dot.append(title);
      svg.append(dot);
    }
    const key = element('span', '● ' + label);
    key.style.color = color;
    legend.append(key);
  });
  box.append(svg, legend);
  return box;
}

function details(label, ...children) {
  const section = element('details');
  section.append(element('summary', label), ...children);
  return section;
}

function distributionChart(rows, fields, paired = true) {
  const label = element('label', '曲线指标 ');
  const select = element('select');
  select.setAttribute('aria-label', paired ? '接触结果曲线指标' : '滚动体运动曲线指标');
  for (const [key, title] of fields) {
    const item = element('option', title);
    item.value = key;
    select.append(item);
  }
  const frame = element('div');
  function plot() {
    const [field, title, unit] = fields.find(([key]) => key === select.value);
    frame.replaceChildren(chart((paired ? [['outer','外圈'],['inner','内圈']] : [[null, title]]).map(([race, name]) => ({
      label:name, points: rows.map(row => {
        const metric = race ? row[race]?.[field] : row[field];
        return valid(metric) ? [row.rolling_element, metric.value] : null;
      }),
    })), '滚动体编号', title + ' (' + unit + ')'));
  }
  select.addEventListener('change', plot);
  plot();
  label.append(select);
  const box = element('div');
  box.append(label, frame);
  return box;
}

function contactChart(rows) {
  return distributionChart(rows, CONTACTS.filter(([key]) => rows.some(row => row.outer?.[key] || row.inner?.[key])));
}

function modelTables(tables) {
  const labels = {capacities:'承载能力（原版模型输出）', basic_life:'基本寿命', modified_life:'修正寿命', life_factors:'寿命修正系数'};
  const names = {outer:'外圈', inner:'内圈', element:'滚动体', bearing:'轴承',
    stress_outer:'外圈应力容量', stress_inner:'内圈应力容量',
    stress_element_outer:'滚动体外侧应力容量', stress_element_inner:'滚动体内侧应力容量',
    load_outer:'外圈载荷容量', load_inner:'内圈载荷容量',
    load_element_outer:'滚动体外侧载荷容量', load_element_inner:'滚动体内侧载荷容量'};
  function column(field) {
    if (names[field]) return names[field];
    const [method, part] = field.split('_');
    return (method === 'tallian' ? 'Tallian' : 'STLE') + ' ' + names[part];
  }
  return details('寿命与承载能力模型',
    element('p', '以下为原版各模型的打印值，适用性尚未核实；有限数值也不代表寿命或承载校核通过。空白为未报告，NaN / Infinity 为不可用。'),
    ...tables.map(item => details(labels[item.id] ?? item.heading,
      table(['模型', ...item.columns.map(field => column(field) + ' (' + item.rows[0].metrics[field].unit + ')')],
        item.rows.map(row => [row.model, ...item.columns.map(field => metricText(row.metrics[field]))])))));
}

function stiffnessChart(rows) {
  const speeds = field => new Set(rows.filter(row => valid(row[field])).map(row => row[field].value));
  const speed = speeds('inner_speed').size > 1 ? 'inner_speed' : speeds('outer_speed').size > 1 ? 'outer_speed' : null;
  const label = speed ? SWEEP.find(([key]) => key === speed)[1] : '扫速工况点（转速未变化）';
  const select = element('select');
  select.setAttribute('aria-label', '扫速结果曲线指标');
  for (const [value, name] of [['stiffness','刚度'], ['displacement','相对位移'], ['speed','内外圈转速']]) {
    const item = element('option', name); item.value = value; select.append(item);
  }
  const frame = element('div');
  const plot = () => {
    const [fields, unit] = select.value === 'displacement' ? [SWEEP.slice(2,5), '相对位移 (m)'] :
      select.value === 'speed' ? [SWEEP.slice(0,2), '转速 (rpm)'] : [SWEEP.slice(5), '刚度 (N/m)'];
    frame.replaceChildren(chart(fields.map(([field, name]) => ({
      label:name,
      points:rows.map(row => valid(row[field]) && (!speed || valid(row[speed])) ?
        [speed ? row[speed].value : row.point, row[field].value] : null),
    })), label, unit));
  };
  const box = element('div'), control = element('label', '曲线指标 ');
  select.addEventListener('change', plot); plot(); control.append(select); box.append(control, frame);
  return box;
}

export function renderAnalysisResult(container, reply, jobId, conditions) {
  const {result, profile, operating_conditions: operating} = reply;
  const contactRows = result.contacts, sweep = result.stiffness_sweep;
  const execution = result.execution.status === 'EXITED_ZERO' ? '已退出 · 退出码 0' : result.execution.status;
  const convergence = result.convergence.status === 'UNKNOWN' ? '未知（缺少独立收敛证据）' : result.convergence.status;
  const statuses = element('p', '进程 ' + execution + ' ｜ 来源哈希已验证 ｜ 支持的结果段已解析 ｜ 收敛 ' + convergence);
  statuses.className = 'analysis-statusline';
  const summary = element('p', '总功率损失 ' + metricText(result.summary.total_power_loss) + ' W ｜ 内部游隙 ' +
    metricText(result.summary.internal_clearance) + ' m');
  const sweepTable = table(['工况点', ...SWEEP.map(([, label]) => label)],
    sweep.map(row => [row.point, ...SWEEP.map(([key]) => metricText(row[key]))]));
  const geometry = [['inner_race_od_mm','分析内圈外径 (mm)'], ['inner_sidewall_mm','内圈分析挡边 (mm)'],
    ['outer_sidewall_mm','外圈分析挡边 (mm)']].filter(([key]) => Object.hasOwn(reply.analysis_geometry, key))
    .map(([key, label]) => [label, String(reply.analysis_geometry[key])]);
  const evidence = details('本次运行的设计、配置和文件来源',
    table(['记录', '值'], [
      ['运行编号', reply.run_id], ['三维作业', jobId], ['设计 SHA-256', reply.request_hash],
      ['参考配置', profile.id], ['参考来源', profile.source], ['参考 DATA SHA-256', profile.sha256],
      ['原版 EXE SHA-256', reply.solver_exe_sha256], ...geometry,
      ...Object.entries(result.files).map(([file, info]) => [file + ' SHA-256', info.sha256 ?? info.status]),
    ]));
  const invalid = result.nonfinite_evidence;
  const contactFields = CONTACTS.filter(([key]) => contactRows.some(row => row.outer?.[key] || row.inner?.[key]));
  // Keep each table narrow enough to compare the two races without 40 columns.
  const contactTables = [];
  for (let i = 0; i < contactFields.length; i += 4) {
    const fields = contactFields.slice(i, i + 4);
    contactTables.push(table(['滚动体', ...fields.flatMap(([, name, unit]) => ['外圈 ' + name + ' (' + unit + ')', '内圈 ' + name + ' (' + unit + ')'])],
      contactRows.map(row => [row.rolling_element, ...fields.flatMap(([key]) => [metricText(row.outer?.[key]), metricText(row.inner?.[key])])])));
  }
  const elements = result.rolling_elements ?? [];
  const elementFields = ELEMENTS.filter(([key]) => elements.some(row => row[key]));
  const more = [];
  if (contactRows.some(row => ['outer','inner'].some(race =>
    Object.values(row[race] ?? {}).some(metric => metric.reason === 'NONPOSITIVE_ABSOLUTE_TEMPERATURE')))) {
    more.push(element('p', '原版部分绝对温度输出为 0 K 或负值，已标为不可用；未将其作为实际油膜温度。原因仍需核实。'));
  }
  if (elementFields.length) more.push(element('h4', '滚动体转速、位置与受力'), distributionChart(elements, elementFields, false),
    details('滚动体运动与受力数据', ...elementFields.map(([key, name, unit]) =>
      table(['滚动体', name + ' (' + unit + ')'], elements.map(row => [row.rolling_element, metricText(row[key])])))));
  if (result.model_tables?.length) more.push(modelTables(result.model_tables));
  const fits = [['outer_race_fit','外圈配合'], ['inner_race_fit','内圈配合']].filter(([key]) => result.summary[key]);
  if (fits.length) more.push(details('内外圈配合', table(['项目','数值 (m)'], fits.map(([key, name]) => [name, metricText(result.summary[key])]))));
  const missing = Object.entries(result.additional_sections ?? {}).filter(([, status]) => status !== 'PARSED');
  if (missing.length) more.push(element('p', '本次输出缺少部分扩展结果段，未提供的指标不会补零。'));
  if (result.raw_report) more.push(details('原版完整结果文本（含补充输出）',
    element('p', 'OUT.txt 自第 ' + result.raw_report.line + ' 行起。尚未结构化的分段保留原文，单位以原表为准；打印内容不代表已通过工程校核。'),
    element('pre', result.raw_report.text)));
  container.replaceChildren(statuses, summary,
    details('本次运行工况', table(['工况', '来源', '生效值'],
      conditions.map(([key, label]) => [label, Object.hasOwn(operating.requested, key) ? '用户输入' : '参考 DATA',
        operating.effective[key]]))),
    element('h4', '接触、润滑与温度分布'), contactChart(contactRows), details('内外圈接触数据', ...contactTables),
    element('h4', '扫速刚度、位移与转速'), stiffnessChart(sweep), details('转速、位移与刚度数据', sweepTable),
    ...more,
    details('非有限输出 · ' + invalid.length + ' 项',
      element('p', '以下 NaN / Infinity 来自原版输出，对应指标不可用，具体原因尚待核实。'),
      table(['文件', '行', '结果段', '模型', '方法', '部件', '原始内容', '状态'],
        invalid.map(item => [item.file, item.line,
          ({'Modified Life with Various Life Models':'修正寿命',
            'Life Modification Factors with Various Life Models':'寿命修正系数'}[item.section] ?? item.section ?? '未映射'),
          item.model ?? '未映射', item.method ?? '未映射',
          ({'Outer Race':'外圈','Inner Race':'内圈','Roll Elem':'滚动体','Bearing':'轴承'}[item.component] ?? item.component ?? '未映射'),
          item.raw, '不可用']))),
    evidence);
}
