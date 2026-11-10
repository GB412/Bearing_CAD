const CONTACTS = [
  ['load', '接触载荷', 'N'], ['stress', '接触应力', 'MPa'],
  ['deflection', '接触变形', 'mm'], ['angle', '接触角', '°'],
];
const SWEEP = [
  ['outer_speed', '外圈转速 (rpm)'], ['inner_speed', '内圈转速 (rpm)'],
  ['displacement_x', 'X 位移 (m)'], ['displacement_y', 'Y 位移 (m)'], ['displacement_z', 'Z 位移 (m)'],
  ['stiffness_xx', 'Kxx (N/m)'], ['stiffness_yy', 'Kyy (N/m)'], ['stiffness_zz', 'Kzz (N/m)'],
];
const COLORS = ['#2479b0', '#c05e29', '#5960b2'];
const valid = metric => metric?.status === 'VALID' && Number.isFinite(metric.value);
const number = value => String(Number(value.toPrecision(8)));
const metricText = metric => valid(metric) ? number(metric.value) : '不可用' + (metric?.raw ? ' (' + metric.raw + ')' : '');

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

function contactChart(rows) {
  const label = element('label', '曲线指标 ');
  const select = element('select');
  for (const [key, title] of CONTACTS.slice(0, 2)) {
    const item = element('option', title);
    item.value = key;
    select.append(item);
  }
  const frame = element('div');
  function plot() {
    const [field, title, unit] = CONTACTS.find(([key]) => key === select.value);
    frame.replaceChildren(chart([['outer','外圈'],['inner','内圈']].map(([race, name]) => ({
      label:name, points: rows.map(row => valid(row[race]?.[field]) ? [row.rolling_element, row[race][field].value] : null),
    })), '滚动体编号', title + ' (' + unit + ')'));
  }
  select.addEventListener('change', plot);
  plot();
  label.append(select);
  const box = element('div');
  box.append(label, frame);
  return box;
}

function stiffnessChart(rows) {
  const speeds = field => new Set(rows.filter(row => valid(row[field])).map(row => row[field].value));
  const speed = speeds('inner_speed').size > 1 ? 'inner_speed' : speeds('outer_speed').size > 1 ? 'outer_speed' : null;
  const label = speed ? SWEEP.find(([key]) => key === speed)[1] : '扫速工况点（转速未变化）';
  return chart(SWEEP.slice(5).map(([field, name]) => ({
    label:name,
    points:rows.map(row => valid(row[field]) && (!speed || valid(row[speed])) ?
      [speed ? row[speed].value : row.point, row[field].value] : null),
  })), label, '刚度 (N/m)');
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
  const contactTable = table(['滚动体', ...CONTACTS.flatMap(([, title, unit]) =>
    ['外圈 ' + title + ' (' + unit + ')', '内圈 ' + title + ' (' + unit + ')'])],
    contactRows.map(row => [row.rolling_element, ...CONTACTS.flatMap(([key]) =>
      [metricText(row.outer?.[key]), metricText(row.inner?.[key])])]));
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
  container.replaceChildren(statuses, summary,
    details('本次运行工况', table(['工况', '来源', '生效值'],
      conditions.map(([key, label]) => [label, Object.hasOwn(operating.requested, key) ? '用户输入' : '参考 DATA',
        operating.effective[key]]))),
    element('h4', '滚动体接触分布'), contactChart(contactRows), details('内外圈接触数据', contactTable),
    element('h4', '扫速刚度'), stiffnessChart(sweep), details('转速、位移与刚度数据', sweepTable),
    details('非有限输出 · ' + invalid.length + ' 项', table(['文件', '行', '原始内容', '状态'],
      invalid.map(item => [item.file, item.line, item.raw, '不可用']))),
    evidence);
}
