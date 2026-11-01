// Original RoBAS DWG four-sheet actions and the dedicated 2D preview workspace.
export function initDrawingWorkbench(getDesign) {
  const $ = name => document.getElementById(name);
  const button = $('generate2d');
  const status = $('drawingStatus');
  const workspaceStatus = $('drawingWorkspaceStatus');
  const tabs = $('drawingSheetTabs');
  const previewStage = $('drawingPreviewStage');
  const previewImage = $('drawingPreviewImage');
  const previewEmpty = $('drawingPreviewEmpty');
  const downloadCurrent = $('drawingDownloadCurrent');

  const sheetTitles = {
    assembly: '总装图',
    outer_ring: '外圈图',
    inner_ring: '内圈图',
    cage: '保持架图',
  };

  let online = false;
  let allowed = new Set();
  let busy = false;
  let generation = 0;
  let controller = null;
  let sheets = [];
  let activeSheet = null;
  let zoom = 1;
  let panX = 0;
  let panY = 0;
  let drag = null;

  function supported() {
    const designType = $('bearingType').value;
    const variant = $('param-configuration')?.value;
    return designType === 'rolling.cylindrical_roller'
      ? allowed.has(designType + ':' + variant)
      : allowed.has(designType);
  }

  function update(message, error = false) {
    status.textContent = message;
    status.classList.toggle('error', error);
    workspaceStatus.textContent = message;
    workspaceStatus.classList.toggle('is-error', error);
    workspaceStatus.classList.toggle('is-ready', !error && message.startsWith('已按原版模板生成'));
    button.disabled = !online || !supported() || busy;
    if (online && !supported() && !busy) {
      const hint = '当前 RoBAS 原版模板暂不支持所选轴承构型';
      status.textContent = hint;
      workspaceStatus.textContent = hint;
    }
  }

  function setWorkspace(name) {
    const drawing = name === 'drawing';
    $('modelWorkspace').hidden = drawing;
    $('drawingWorkspace').hidden = !drawing;
    $('workspace3dTab').classList.toggle('is-active', !drawing);
    $('workspace2dTab').classList.toggle('is-active', drawing);
    $('workspace3dTab').setAttribute('aria-selected', String(!drawing));
    $('workspace2dTab').setAttribute('aria-selected', String(drawing));
    window.dispatchEvent(new Event('resize'));
  }

  function setPreviewEmpty(title, message) {
    $('drawingPreviewEmptyTitle').textContent = title;
    $('drawingPreviewEmptyText').textContent = message;
    previewEmpty.hidden = false;
    previewImage.hidden = true;
    $('drawingCanvasHint').hidden = true;
  }

  function resetZoom() {
    zoom = 1;
    panX = 0;
    panY = 0;
    applyTransform();
  }

  function clampPan() {
    const bounds = previewStage.getBoundingClientRect();
    const maxX = Math.max(0, bounds.width * (zoom - 1) / 2);
    const maxY = Math.max(0, bounds.height * (zoom - 1) / 2);
    panX = Math.max(-maxX, Math.min(maxX, panX));
    panY = Math.max(-maxY, Math.min(maxY, panY));
  }

  function applyTransform() {
    previewImage.style.transform = 'translate3d(' + panX + 'px,' + panY + 'px,0) scale(' + zoom + ')';
    $('drawingZoomLabel').textContent = Math.round(zoom * 100) + '%';
    previewStage.classList.toggle('is-zoomed', zoom > 1.001);
    $('drawingCanvasHint').hidden = !activeSheet;
  }

  function changeZoom(factor) {
    if (!activeSheet) return;
    zoom = Math.max(1, Math.min(5, zoom * factor));
    if (zoom <= 1.001) {
      zoom = 1;
      panX = 0;
      panY = 0;
    } else {
      clampPan();
    }
    applyTransform();
  }

  function clearResults() {
    sheets = [];
    activeSheet = null;
    tabs.replaceChildren();
    const placeholder = document.createElement('span');
    placeholder.className = 'drawing-tabs-placeholder';
    placeholder.textContent = '生成成功后显示图纸列表';
    tabs.append(placeholder);
    previewImage.onload = null;
    previewImage.onerror = null;
    previewImage.removeAttribute('src');
    setPreviewEmpty('暂无二维图纸', '请在左侧填写轴承图纸参数，然后生成原版模板二维图纸。');
    $('drawingTabCount').textContent = '等待生成';
    $('drawingWorkspaceSubtitle').textContent = '生成图纸后，在这里查看四张原版模板图纸。';
    $('drawingSheetTitle').textContent = '尚未选择图纸';
    $('drawingSheetFile').textContent = '生成后显示 DXF 文件名';
    downloadCurrent.hidden = true;
    downloadCurrent.removeAttribute('href');
    resetZoom();
  }

  function localAssetUrl(value, label) {
    if (typeof value !== 'string' || !value.trim()) {
      throw new Error('缺少' + label + '地址');
    }
    const url = new URL(value, window.location.href);
    if (url.origin !== window.location.origin) {
      throw new Error(label + '地址不是本地 CAD 服务地址');
    }
    return url.href;
  }

  function titleFor(sheet) {
    return sheetTitles[sheet.view] || sheet.view || sheet.file;
  }

  function activateSheet(key) {
    const sheet = sheets.find(item => item.key === key);
    if (!sheet) return;
    activeSheet = sheet;
    tabs.querySelectorAll('[role="tab"]').forEach(tab => {
      const selected = tab.dataset.sheetKey === sheet.key;
      tab.classList.toggle('is-active', selected);
      tab.setAttribute('aria-selected', String(selected));
    });
    $('drawingSheetTitle').textContent = sheet.title;
    $('drawingSheetFile').textContent = sheet.file;
    downloadCurrent.href = sheet.downloadUrl;
    downloadCurrent.download = sheet.file;
    downloadCurrent.hidden = false;
    previewImage.alt = sheet.title + ' · ' + sheet.file + ' · 原版 DWG 模板 SVG 预览';
    previewImage.onload = () => {
      previewEmpty.hidden = true;
      previewImage.hidden = false;
      $('drawingCanvasHint').hidden = false;
      applyTransform();
    };
    previewImage.onerror = () => {
      setPreviewEmpty('SVG 预览暂不可用', 'DXF 文件仍可下载；请检查预览文件是否成功生成。');
    };
    previewImage.hidden = false;
    previewEmpty.hidden = true;
    previewImage.src = sheet.previewUrl;
    resetZoom();
  }

  function renderSheets(manifest, fileUrls) {
    if (!Array.isArray(manifest.sheets) || manifest.sheets.length !== 4) {
      throw new Error('出图结果不完整：预期得到四张 DXF 图纸');
    }
    const seen = new Set();
    sheets = manifest.sheets.map(sheet => {
      if (!sheet || typeof sheet.file !== 'string' || !sheet.file) {
        throw new Error('图纸成果清单包含无效文件项');
      }
      const key = String(sheet.view || sheet.file);
      if (seen.has(key)) throw new Error('图纸成果清单包含重复视图');
      seen.add(key);
      return {
        key,
        view: String(sheet.view || ''),
        title: titleFor(sheet),
        file: sheet.file,
        downloadUrl: localAssetUrl(fileUrls?.[sheet.file], sheet.file),
        previewUrl: localAssetUrl(fileUrls?.[sheet.preview_file], sheet.file + ' SVG 预览'),
      };
    });

    tabs.replaceChildren();
    for (const sheet of sheets) {
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.className = 'drawing-sheet-tab';
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', 'false');
      tab.dataset.sheetKey = sheet.key;
      const title = document.createElement('strong');
      title.textContent = sheet.title;
      const file = document.createElement('small');
      file.textContent = sheet.file;
      tab.append(title, file);
      tab.addEventListener('click', () => activateSheet(sheet.key));
      tabs.append(tab);
    }

    $('drawingTabCount').textContent = '4 张已生成';
    $('drawingWorkspaceSubtitle').textContent = '已生成四张原版模板图纸。选择上方图纸标签可切换预览。';
    $('drawingWorkspaceStatus').textContent = '已生成 4 张 DXF';
    $('drawingWorkspaceStatus').classList.remove('is-error');
    $('drawingWorkspaceStatus').classList.add('is-ready');
    activateSheet(sheets[0].key);
  }

  function invalidate(message = '参数已修改，请重新生成二维图纸') {
    generation += 1;
    if (controller) {
      controller.abort();
      controller = null;
    }
    busy = false;
    clearResults();
    update(message, !online);
  }

  async function refresh() {
    try {
      const response = await fetch('/api/v2/cad/drawings/status', {cache: 'no-store'});
      const data = await response.json();
      online = response.ok && data.available === true;
      allowed = new Set(data.supported_bearings || []);
      const failures = Array.isArray(data.failures) ? data.failures : [];
      const detail = failures.length ? '：' + failures.join('；') : '';
      update(online ? '原版 RoBAS DWG 图纸服务已就绪' : '原版出图引擎未就绪' + detail, !online);
    } catch {
      online = false;
      update('RoBAS 二维图纸服务暂不可用', true);
    }
  }

  button.addEventListener('click', async () => {
    if (button.disabled) return;
    const sequence = ++generation;
    controller?.abort();
    controller = new AbortController();
    const signal = controller.signal;
    busy = true;
    update('正在使用原始 DWG 模板生成四张 DXF…');
    clearResults();
    try {
      const drawing = {
        model: $('drawingModel').value.trim(),
        accuracy_class: $('drawingAccuracy').value,
        diameter_series: $('drawingSeries').value,
      };
      if (!drawing.model) throw new Error('请填写轴承型号');
      for (const [id, key] of [['drawingChamfer1', 'chamfer1_mm'],
                               ['drawingChamfer2', 'chamfer2_mm']]) {
        const raw = $(id).value.trim();
        if (raw) {
          const number = Number(raw);
          if (!Number.isFinite(number) || number <= 0) throw new Error('倒角应为正数');
          drawing[key] = number;
        }
      }
      const design = getDesign();
      const response = await fetch('/api/v2/cad/drawings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({design, drawing}),
        signal,
      });
      const reply = await response.json();
      if (sequence !== generation) return;
      if (!response.ok) {
        const code = reply?.error?.error_code || reply?.error?.code;
        if (code === 'CADIMPORT_LICENSE_REQUIRED') {
          throw new Error('CADImport 未完成授权注册，无法打开原版 DWG 模板');
        }
        throw new Error(reply?.error?.message || '二维出图失败');
      }
      if (typeof reply.manifest_url !== 'string' || typeof reply.request_hash !== 'string') {
        throw new Error('二维出图服务返回了无效成果信息');
      }
      const manifestUrl = localAssetUrl(reply.manifest_url, '成果清单');
      const manifestResponse = await fetch(manifestUrl, {cache: 'no-store', signal});
      if (!manifestResponse.ok) throw new Error('DXF 成果清单不可用');
      const results = await manifestResponse.json();
      if (sequence !== generation) return;
      if (results.manifest?.request_hash !== reply.request_hash) {
        throw new Error('成果参数不一致');
      }
      renderSheets(results.manifest, results.file_urls || {});
      setWorkspace('drawing');
      update('已按原版模板生成四张 DXF（未作制造批准）');
    } catch (error) {
      if (sequence === generation && error.name !== 'AbortError') {
        clearResults();
        update('二维出图失败：' + error.message, true);
      }
    } finally {
      if (sequence === generation) {
        busy = false;
        controller = null;
        update(status.textContent, status.classList.contains('error'));
      }
    }
  });

  $('workspace3dTab').addEventListener('click', () => setWorkspace('model'));
  $('workspace2dTab').addEventListener('click', () => setWorkspace('drawing'));
  $('drawingZoomIn').addEventListener('click', () => changeZoom(1.2));
  $('drawingZoomOut').addEventListener('click', () => changeZoom(1 / 1.2));
  $('drawingFit').addEventListener('click', resetZoom);

  previewStage.addEventListener('wheel', event => {
    if (!activeSheet) return;
    event.preventDefault();
    changeZoom(event.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, {passive: false});

  previewStage.addEventListener('pointerdown', event => {
    if (zoom <= 1.001 || !activeSheet) return;
    drag = {x: event.clientX, y: event.clientY, panX, panY};
    previewStage.classList.add('is-dragging');
    previewStage.setPointerCapture(event.pointerId);
  });
  previewStage.addEventListener('pointermove', event => {
    if (!drag) return;
    panX = drag.panX + event.clientX - drag.x;
    panY = drag.panY + event.clientY - drag.y;
    clampPan();
    applyTransform();
  });
  const stopDrag = () => {
    drag = null;
    previewStage.classList.remove('is-dragging');
  };
  previewStage.addEventListener('pointerup', stopDrag);
  previewStage.addEventListener('pointercancel', stopDrag);
  previewStage.addEventListener('lostpointercapture', stopDrag);

  $('bearingType').addEventListener('change', () => invalidate('轴承类型已改变，请重新生成二维图纸'));
  for (const id of ['parameters', 'cageParams', 'drawingControls']) {
    const element = $(id);
    element.addEventListener('input', () => invalidate());
    element.addEventListener('change', () => invalidate());
  }
  for (const id of ['cageEnabled', 'cageKind']) {
    $(id).addEventListener('change', () => invalidate());
  }

  clearResults();
  refresh();
}
