# Bearing CAD 本地运行与审查说明

本仓库可以直接提交到 GitHub。仓库内包含前端、Python API、RoBAS 变量处理代码、CADImport 桥接源码、测试和启动脚本。

原始 RoBAS 资源和 CADImport 是外部依赖，不复制进仓库，也不应提交到 GitHub：

- `RoBAS_Resources`：DWG 模板、SQLite 数据库、CSV 系数表和 SHX 字体。
- `CADImport.dll`：商业 CADImport 程序集。
- `bridge/cadimport/bin`：本机编译输出，不提交。
- `dist`、`artifacts`、`node_modules`：本机生成目录，不提交。

## 目录结构

```text
Bearing_CAD/
├─ bearing_cad/                  滚动轴承 Python API、几何、图纸变量及导出流程
├─ bridge/cadimport/             CADImport 桥接源码（不含商业 DLL 和编译输出）
├─ config/                       可提交的本地配置示例；真实配置由 Git 忽略
├─ docs/
│  ├─ assets/                    文档配图
│  ├─ migration/                 三维迁移记录与验收材料
│  ├─ planning/                  实施计划和任务书
│  └─ v2/                        CAD V2 设计与验收文档
├─ outputs/                      固定初始参数的已跟踪 CAD-01 下载示例
├─ scripts/                      环境预检、桥接构建及启动脚本
├─ tests/                        CAD-01/CAD-02/CAD-03 Python 测试
├─ tests_v2/                     滚动轴承、RoBAS 图纸和参数合同测试
├─ tests-browser/                Playwright 页面及二维预览测试
├─ tests-browser-real/           调用真实本地 CAD API 的浏览器测试
├─ index.html, app.js, geometry.js
│                                 CAD-01 Vite 入口及前端模块
├─ rolling.html, rolling_*.js, viewer.js, rolling_workbench.css
│                                 滚动轴承工作台前端模块
├─ cad02_*.py, cad03*.py/js       CAD-02/CAD-03 演示模块
├─ package.json / package-lock.json
│                                 Vite、Three.js、Playwright 与锁定依赖
└─ environment-v2.yml / requirements-cad.txt
                                  Python CAD 环境定义

本机生成目录（Git 忽略）：`node_modules/`、`dist/`、`artifacts/`、`build/`、`test-results/` 和 Python 缓存。`outputs/` 是例外：其中固定 STEP 和相关快照由 CAD-01 页面及构建测试使用，保持跟踪；其他 CAD API 生成结果应写入 `artifacts/`。

字体等本机外部资源放在仓库之外。当前可选字体副本位于 `D:\Bearing CAD\fonts\robas`，不可提交到仓库；RoBAS DWG、SQLite、CSV 和 CADImport DLL 也继续使用外部授权资源目录。
```

## 1. 前端和三维演示

在 PowerShell 中执行：

```powershell
cd "D:\Bearing CAD\Bearing_CAD"
npm ci
npm run build
npm run dev
```

打开 Vite 输出的地址。生产构建可以使用：

```powershell
npm run preview -- --host 127.0.0.1
```

没有 RoBAS 资源时，三维工作台仍可运行；只有二维原版 DWG 出图按钮不可用。

## 2. Python CAD 环境

推荐使用项目环境文件：

```powershell
conda env create -f environment-v2.yml
conda activate bearing-cad-v2
python -m pip install -r requirements-cad.txt
```

如果环境已经存在：

```powershell
conda activate bearing-cad-v2
python -m pip install -r requirements-cad.txt
```

`Pillow` 是 `ezdxf` SVG 网页预览所需依赖。没有它时，API 会在导入图纸模块阶段失败。

## 3. 配置 RoBAS 二维出图

先从原始完整项目取得资源目录和受授权的 `CADImport.dll`。复制配置示例为本地配置，仅用于记录路径：

```powershell
Copy-Item config/robas.local.example.json config/robas.local.json
```

编辑 `config/robas.local.json`，替换 `resources_path` 和 `cadimport_dll_path`。真实配置已被 Git 忽略。

在 Windows x64 上执行预检：

```powershell
.\scripts\check_robas_environment.ps1 `
  -ResourcesPath "D:\path\to\RoBAS_Resources" `
  -CadImportDllPath "D:\path\to\CADImport.dll"
```

预检会检查 DWG 签名、SQLite 表、CSV、字体、DLL 版本、MSBuild 和 .NET Framework 4.5.2 Targeting Pack，并写入 `artifacts/cadimport/environment_report.json`。

编译桥接程序：

```powershell
.\scripts\build_cadimport_bridge.ps1 `
  -CadImportDllPath "D:\path\to\CADImport.dll"
```

启动完整网页工作台：

```powershell
.\scripts\start_bearing_cad_with_robas.ps1 `
  -ResourcesPath "D:\path\to\RoBAS_Resources" `
  -CadImportBridgePath ".\bridge\cadimport\bin\Release\CadImportBridge.exe" `
  -Python "python" `
  -Port 8090
```

打开 `http://127.0.0.1:8090/rolling.html`。生成二维图纸后，网页展示来自生成 DXF 的 SVG 预览，同时提供四张 DXF 下载。SVG 只是浏览器预览，DXF 才是 CADImport 输出文件。

在已经填写 `config/robas.local.json` 的本机，也可以使用一条命令完成预检、桥接编译和启动：

```powershell
.\scripts\run_bearing_cad_with_robas.ps1
```

该文件只记录本机路径，已被 `.gitignore` 排除；提交 GitHub 时只提交 `config/robas.local.example.json`。

## 4. 验证命令

源码和不依赖商业 DLL 的检查：

```powershell
npm run build
npm run test:unit:js
python -m pytest -q tests_v2
git diff --check
```

具备 Windows CADImport 环境时，额外执行：

```powershell
.\bridge\cadimport\bin\Release\CadImportBridge.exe doctor
.\bridge\cadimport\bin\Release\CadImportBridge.exe inspect "D:\path\to\0_00KS.DWG"
```

只有真实 `inspect`、TEXT 替换、DXF 解析和 CAD 查看器打开均完成后，才能报告二维链路通过。当前输出保留 `Demo / 未作制造批准` 标识，不等同于经过 GB/ISO 工程审图的制造图。

## 给其他 AI 的审查入口

建议先阅读：

1. `README.md`
2. `docs/LOCAL_SETUP.md`
3. `bearing_cad/drawing_runner.py`
4. `bearing_cad/drawing_http.py`
5. `bridge/cadimport/Program.cs`
6. `scripts/check_robas_environment.ps1`
7. `scripts/build_cadimport_bridge.ps1`
8. `scripts/start_bearing_cad_with_robas.ps1`

审查时应区分：三维 OCCT/CadQuery 生成、原版 RoBAS DWG TEXT 替换、DXF 下载和浏览器 SVG 预览；它们不是同一个几何生成引擎。
