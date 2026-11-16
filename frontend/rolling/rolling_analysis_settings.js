const MATERIALS = {
  rolling_elements: '滚动体', outer_race: '外圈', inner_race: '内圈',
  cage: '分析保持架', shaft: '轴', housing: '轴承座',
};
const LABELS = {
  density_kg_m3: '密度 (kg/m³)', elastic_modulus_gpa: '弹性模量 (GPa)', poisson_ratio: '泊松比',
  thermal_expansion_per_k: '热膨胀系数 (1/K)', specific_heat_j_kg_k: '比热容 (J/kg/K)',
  conductivity_w_m_k: '热导率 (W/m/K)', pocket_viscosity_pa_s: '兜孔动力黏度 (Pa·s)',
  guide_viscosity_pa_s: '保持架引导面动力黏度 (Pa·s)', load_steps: '载荷步数',
};

function groups(settings) {
  return [
    ...Object.entries(MATERIALS).map(([role, label]) =>
      [label, ['materials', role], settings.materials?.[role]]),
    ['保持架润滑', ['lubrication'], settings.lubrication],
    ['求解控制', ['solver'], settings.solver],
  ].filter(([, , fields]) => fields && Object.keys(fields).length);
}

export function showSettingsFields(container, defaults) {
  container.replaceChildren();
  if (!defaults) {
    container.textContent = '请选择可用的原版参考配置。';
    return;
  }
  for (const [name, path, fields] of groups(defaults)) {
    const section = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = name;
    const grid = document.createElement('div');
    grid.className = 'fields';
    for (const [key, value] of Object.entries(fields)) {
      if (!Object.hasOwn(LABELS, key)) continue;
      const label = document.createElement('label');
      label.className = 'field';
      label.textContent = LABELS[key];
      const input = document.createElement('input');
      input.id = 'analysis-' + [...path, key].join('-');
      input.type = 'number';
      input.step = key === 'load_steps' ? '1' : 'any';
      input.placeholder = String(value);
      input.dataset.setting = [...path, key].join('/');
      label.append(input);
      grid.append(label);
    }
    section.append(summary, grid);
    container.append(section);
  }
}

export function readSettingsFields(container) {
  const settings = {};
  for (const input of container.querySelectorAll('input[data-setting]')) {
    const path = input.dataset.setting.split('/');
    const field = path.pop();
    if (input.validity.badInput || input.validity.stepMismatch) throw Error(LABELS[field] + '输入无效。');
    if (input.value === '') continue;
    const fields = path.reduce((node, part) => (node[part] ??= {}), settings);
    fields[field] = Number(input.value);
  }
  return settings;
}

export function settingsRows(settings) {
  if (!settings) return [];
  return groups(settings.effective).flatMap(([name, path, fields]) => {
    const requested = path.reduce((node, part) => node?.[part], settings.requested);
    return Object.entries(fields).map(([field, value]) =>
      [name, LABELS[field], Object.hasOwn(requested ?? {}, field) ? '用户输入' : '参考 DATA', value]);
  });
}
