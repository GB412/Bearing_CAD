# BearingCAD Studio — 滑动轴承演示 + 滚动轴承三维参数化 CAD

这个仓库包含**两个不同的工作台**：

- **滚动轴承三维工作台**（`rolling.html`）：深沟球、圆柱滚子 N/NU/NJ/NF/NUP、角接触球三类功能级三维模型；可选对应保持架、独立零件、真实 CadQuery/OCCT B-Rep、STEP/STL、几何质量与参数快照。
- **滑动轴承 CAD-01 演示**（`index.html`）：原有径向滑动轴承的示意二维视图和三维演示。该模块与滚动轴承 CAD 后端彼此独立。

**明确范围：截至 3D-MIG-09 为止只交付独立 CAD 工具，不接入多 Agent 轴承设计系统；不扩展滚动轴承正式二维工程图，也不宣称已经通过轴承载荷、寿命或制造审核。**

## 滚动轴承：Windows 本地运行

前提：Node.js 20+；Miniforge/Micromamba/Conda；可创建 `environment-v2.yml` 中的 Python 3.11 + CadQuery 固定环境；需有本地浏览器。

```powershell
conda env create -f environment-v2.yml
conda activate bearing-cad-v2
npm ci
npm run build
python -m bearing_cad.api --port 8090 --static dist
```

如果 `bearing-cad-v2` 环境已经存在，则跳过首次 `conda env create`（必要时显式更新依赖，避免覆盖现有环境）。

然后访问 **http://127.0.0.1:8090/rolling.html**，选择轴承类型及构型、勾选保持架（可选），输入几何参数，点击“生成精确 CAD 模型”。三维查看器可旋转、透明、半剖、爆炸、单零件显隐；成果区可下载 `bearing_assembly.step`、STL、`design_snapshot.json`、`artifact_manifest.json` 和 `geometry_quality.json`。

首次构建时 `npm ci` 和 Conda 依赖下载需要网络；**运行时默认不加载外部 CDN**，但是本地 CAD 服务必须持续运行。后端只监听 **127.0.0.1**，是单机演示程序，不是公网生产 API。

### 工程约束

页面预置的几何参数来自回归测试夹具，**不是厂家标准轴承型号或推荐工艺参数**。`stamping_double_half` 的 `board_thickness_mm` 当前只表示球兜外最小轴向余料约束，而非实测全域均匀板厚。STEP 体积回读容差是几何交换检查，不是生产制造公差。

目前师兄 RoBAS Eyeshot 原版 STEP 实体未提供，因此新旧模型**不能宣称 1:1 几何等价**。只有旧版 C# 源码追踪以及当前 OCCT 七组基准证据。FreeCAD 独立软件打开的人工验收状态应以 `docs/migration/3d-mig-09b-freecad.md` 实际记录为准，不可把准备的脚本当成通过结果。

## RoBAS 原版二维图纸（可选 Windows 功能）

滚动轴承工作台新增独立“二维图纸 · RoBAS 模板”区域，沿用原 DWG 哑图、SQLite 变量表、`CADText.Text` 精确替换与 DXF 导出流程。此功能与现有三维 OCCT 工作流相互独立，**不依据三维模型重画二维轮廓**。

原二维桥接目前仍在 [PR #38](https://github.com/GB412/Bearing_CAD/pull/38) 等待真实 Windows 编译/授权及原图 DWG→DXF 实机验收，故**不能宣称已通过 12 张图纸端到端验收**。需要从该 PR 取得桥接源码，在 Windows + .NET Framework 4.5.2 + 原 CADImport.dll 正式编译并验证输出。不能提交授权 DLL、原 DWG、原 SQLite 到公共仓库。

桥接验收通过后，在原有命令后增加两个本地参数：

```powershell
python -m bearing_cad.api --port 8090 --static dist \
  --robas-resources "D:\\RoBAS_Resources" \
  --cadimport-bridge "D:\\Bridge\\CadImportBridge.exe"
```

未配置上述环境时，工作台二维按钮会显示不可用，已有三维 STEP/STL 建模和下载功能正常。配置完成后二维工作台使用相同的`bearing-cad.request.v1`参数，输入型号、精度和直径系列并调用原版 DWG 模板替换，结果下载总图、外圈、内圈、保持架四张 DXF。原版 RoBAS 特有的沟道、挡边和保持架参数若不在现有 CAD 参数合同中，需要由原版计算逻辑或显式设计上下文提供；不猜测缺失值。圆柱滚子第一版仅启用原版 N 型模板。输出属于原版模板文字替换结果，不代表重新建立的二维参数化几何。

开发者也可使用独立命令行 `python -m bearing_cad.drawing_cli --request design_and_drawing.json --resources ... --bridge ... --out ...` 生成并核验 DXF。

## 测试与验收

在 CadQuery 环境下运行：

```powershell
python -m unittest discover -s tests_v2 -p "test_*.py" -v
python -m bearing_cad.migration_baseline --output build/migration-07a
node --test rolling_manifest.test.js
```

**真实网页与 CAD 内核端到端**（需已执行 `npm ci`、`npm run build`，并安装 Playwright Chromium）：

```powershell
npx playwright install chromium
npx playwright test --config playwright.rolling.real.config.js
```

最后的脚本自动启动真实本地 Python API，并在浏览器中运行：深沟球双半笼 26 实例、圆柱 NUP 有笼 15 实例、角接触球有笼 14 实例、STEP 下载及错误清理。该测试需要空闲 8090 端口。

使用 FreeCAD 独立打开 `build/migration-07a/bundles/<artifact_key>/bearing_assembly.step` 的步骤，见 [FreeCAD 人工验收说明](docs/migration/3d-mig-09b-freecad.md)。**软件 GUI 人工核查不能由 GitHub CI 自动模拟。**

## 滑动轴承 CAD-01 演示（保留既有工作流）

```powershell
npm ci
npm run dev
```

根据 Vite 终端输出打开开发服务器，或运行 `npm run preview` 预览构建后的 `index.html`。它保留二维 SVG/DXF 示意、Three.js 三维查看及原 CAD-01 示例生成器。原有滑动轴承模块的演示 STEP 可能使用固定参数，不应误认为实时按网页参数重建。

## 版本、模块与交付记录

- 原始 CAD-01 工作台不被 3D-MIG 阶段改写。
- 三类滚动轴承及详细保持架迁移：3D-MIG-01～05。
- STEP 几何质量/装配变换：3D-MIG-06、08A。
- RoBAS 源码对照/七组现有模型基线：3D-MIG-07A；缺失原版 Eyeshot 实体的 07B 保持未验证。
- 真实浏览器-CAD 服务联调与交付候选：3D-MIG-09A～C。
- **多 Agent 集成（原 PR10）暂停，滚动轴承正式二维工程图暂停。**

具体发行验收状态与限制请查阅 [3D-MIG-09 交付说明](docs/migration/3d-mig-09-release.md)。
