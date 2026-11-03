# RoBAS 原版字体与 SVG 预览

## 字体依赖检查（2026-11-02）

使用原版 DWG 经 CADImport 导出的样式表与实际生成的 DXF 对照：深沟球、角接触球、圆柱滚子 N 型，共 12 张图纸的字体引用一致。未修改 DWG、DXF、TEXT 替换算法或二维几何。

| 文字样式 | 主字体 font | 大字体 bigfont | 本地查找结果 |
| --- | --- | --- | --- |
| `HZ` | `SIMPLEX` | `HZTXT` | 原版资源中均存在；AutoCAD 安装字体目录有 simplex.shx，没有 hztxt.shx |
| `Standard` / `STANDARD` | `txt` | 空 | 原版资源和 AutoCAD 字体目录中均有 txt.shx |

`HZTXT` 是 `HZ` 样式的 **bigfont**，负责扩展/中文字形，不能当成主字体替换。深沟球 assembly、outer_ring、inner_ring、cage 中使用 `HZ` 的 TEXT 数量分别为 198、139、123、95；内圈另有 3 个 TEXT 使用 Standard，其他深沟球图纸无 TEXT 使用 Standard。

本机找到两份相同的原版 `hztxt.shx`：

```text
D:\RotorStudio\ui_rotorstudio-9857bcc7afce658be15dfd2b559a55cb12b55bbd\NetLib\RoBAS_Resources\Resource\shx\hztxt.shx
D:\RotorStudio\ui_rotorstudio-9857bcc7afce658be15dfd2b559a55cb12b55bbd\NetLib\DLAP_Resources\shx\hztxt.shx
```

文件大小均为 1,171,617 bytes，SHA-256 为 `95f9ec57eede9095a2dc738ef5034887dc42c3dece048724bc602ff7994144c7`。未复制、下载或提交字体文件。原版资源随本机安装提供，不能据此推定有向 GitHub 再分发的许可。

本地检查报告位于被 Git 忽略的 `artifacts/font-svg-review/font-preview-report.json`，记录每张图纸的所有 STYLE、font/bigfont、TEXT 使用数量、字体查找结果、校验值及 DXF 审计。搜索了以下路径中的 633 个字体文件：

- 上述 RoBAS 的 `Resource\shx`。
- 上述 DLAP 的 `shx`。
- `D:\AutoCAD\AutoCAD 2025\Fonts`。
- `C:\Windows\Fonts`。

## AutoCAD 配置与人工验收

1. 在 AutoCAD 输入 `OPTIONS`，打开“文件 → 支持文件搜索路径”。
2. 添加上述完整的 RoBAS `Resource\shx` 目录（目录，不是单个文件）。保留已有路径。
3. 应用设置，关闭并重新打开原始生成的 DXF；不要保存临时替换后的图纸覆盖原文件。
4. 检查是否还提示缺失字体。使用 `STYLE` 检查 `HZ` 的主字体仍为 SIMPLEX、大字体仍为 HZTXT。
5. 放大技术条件、标题栏、尺寸和形位公差符号，人工确认中文、字宽、符号及布局。

AutoCAD 缺失提示说明该字体引用未能被解析；原字体在安装目录之外的师兄资源中，而不是资源根本不存在。添加路径后的实际加载和符号效果仍需完成 GUI 验收。本次桌面工具启动 AutoCAD 返回 `accessibility window-opened handler did not become ready`，且未发现可操作的 AutoCAD 窗口，**不能声称已消除字体提示**。之前使用 gbcbig.shx 打开的可读画面也不能证明 HZTXT 已加载。

若另一台电脑确实没有原字体，明确保留缺失状态。只在独立 DXF 副本上人工试验已安装的 `txt.shx + gbcbig.shx` 等组合；这不是等价替换，可能改变字形、文字宽度、间距和工程符号。不自动或永久修改原 DXF 的字体引用。

## SVG 偏左与异常留白的原因及修复

CADImport 的实际 TEXT 中包含 `\M+5C9EE` 这样的 MIF 编码（代码页 5 / cp936）。原 ezdxf 绘图前端将这些序列按可见字符处理，使中文说明变成很长的文字边界。自动页面把这些错误边界算入，导致右侧留白及图框偏左。`layout.Page(0, 0)` 本身支持自动页面，并非固定使用纸张大小就能解决。

另外，ezdxf 1.4.2 的 `Textstyle.make_font()` 明确忽略 bigfont，不能组合 SIMPLEX 与 HZTXT 显示中文。现在仅在 SVG 显示副本中解码 MIF，并从已经安装的宋体、微软雅黑、黑体或 Noto CJK 选择字体；SVG 使用矢量字形路径，无需网页下载字体。未找到支持的字体时记录日志，中文可能缺字。即使有替代字体，字形及工程符号仍不能保证与 AutoCAD 原版 SHX 完全一致。

每张图独立取得 SVGBackend 实际记录的内容边界，四周增加内容长边的 4% 作为边距，再显式传入 render_box。不使用 DXF 保存的视口、LIMMAX 或未经解码的文字估计。保留全部可渲染实体，未检测到需要删除或裁掉的远处实体；若其他图纸出现这种情况，应检查其实体/图层来源，不能直接删除原实体。

在相同 DXF 上对比旧渲染与修复后页面范围：

| 深沟球图纸 | 旧页面 mm | 修复后 mm |
| --- | --- | --- |
| assembly | 316.9 × 300 | 234 × 324 |
| outer_ring | 373.3 × 315 | 234 × 324 |
| inner_ring | 364.3 × 300 | 234 × 324 |
| cage | 328.2 × 300 | 234 × 324 |

圆柱滚子 cage 旧页面达到 694.5 × 297 mm，修复后为 233.8 × 320.8 mm。以上均保留原图框、技术条件和标题栏，没有通过裁切制造居中效果。

前端以 SVG 自然比例在画布中居中，缩放/平移约束使用实际显示的图像尺寸。切换图纸重置为适应窗口，窗口大小及二维/三维标签变化时重新约束平移。保留放大、缩小、滚轮、拖拽及适应窗口按钮。

更新后需要重新构建前端、重启 Python API 并重新生成图纸。SVG 缓存版本已更新，避免继续返回旧预览；旧成果目录不自动改写，DXF 内容不因预览版本改变而修改。

## 回归与验收复现

使用现有装有 CadQuery 2.5.2 / ezdxf 1.4.2 的 Python 环境：

```powershell
python -m pytest -q tests_v2/test_drawing_svg_preview.py
npm ci
npm run build
npm run test:browser
python -m pytest -q tests_v2
npx playwright test --config playwright.rolling.real.config.js
```

指定本地真实 CADImport 生成的四张 DXF/SVG 目录，运行预览及下载校验（未指定时该用例跳过，不代表验收通过）：

```powershell
$env:BEARING_DRAWING_FIXTURES = "D:\Bearing CAD\Bearing_CAD\artifacts\font-svg-review\drawings\<bundle_key>"
npx playwright test tests-browser/drawing_preview.spec.js -g "local CADImport" --workers=1
```

该测试使用真实 SVG/DXF 文件，状态及任务接口使用测试响应；不应描述成浏览器触发 CADImport 的端到端测试。分别为三类轴承指定目录，共覆盖 12 张图纸和 1440 × 1000、390 × 844 两种浏览器视口。检查图像居中、不溢出、缩放、平移、适应窗口、切换图纸与二维/三维标签，并逐文件核对下载 SHA-256。图纸内容完整性同时依靠截图目检，不由下载成功推断。

本次全量 Python 回归为 147 passed / 3 failed；在干净的 main `9ec7fa3` 副本上复现同样的 3 个失败：`test_robas_stamped_shell.py` 的两处 Compound.val() 调用，以及 `test_stamping_cage.py` 的旧参数拒绝断言。它们属于已有三维保持架测试问题，本次没有改动相关代码；不能将全量三维测试写成全部通过。

本机实际执行结果：

| 检查 | 结果 |
| --- | --- |
| `npm ci` / `npm run build` | 成功；npm 报告 3 项 high 安全公告，构建有大包提示，本次未升级依赖 |
| 新增 SVG Python 用例 | 8 passed |
| RoBAS 二维回归（含新增用例） | 83 passed |
| `npm test`（CadQuery 环境）/ `npm run test:unit:js` | 19 / 4 passed |
| `npm run test:browser` | 14 passed、1 skipped（本地真实资源用例） |
| 单独指定三类真实 DXF/SVG 的浏览器用例 | 3 passed，共 12 张图、两种视口 |
| 真实 Python CAD API 三维浏览器回归 | 2 passed，含 STEP/STL 导出 |
| 12 张原始 DXF | 致命审计错误为 0，SHA-256 均未变化，原版字体引用保持一致 |
| AutoCAD 加载原字体后的 GUI 复核 | 未验证，桌面启动工具未能取得窗口；需按上述步骤人工检查 |

成果继续标记为 Demo / 未经制造批准。SVG 是显示辅助，不代替原 DXF 或 AutoCAD 工程复核。
