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
├─ bearing_cad/                 Python API、参数合同、变量映射和导出流程
├─ bridge/cadimport/            .NET Framework 4.5.2 CADImport 桥接源码
├─ config/                      本地配置示例，不含真实路径或授权信息
├─ scripts/                     预检、桥接编译和启动脚本
├─ tests_v2/                    Python 单元测试和 RoBAS 测试
├─ tests-browser/               Playwright 浏览器测试
├─ rolling.html                 滚动轴承三维和 RoBAS 二维工作台
├─ index.html                   CAD-01 滑动轴承演示入口
├─ package.json                 Vite、Three.js、Playwright 依赖
├─ package-lock.json            固定 Node 依赖版本
└─ requirements-cad.txt         Python CAD/DXF/SVG 依赖
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
