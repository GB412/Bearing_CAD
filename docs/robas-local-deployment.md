# 本地部署结构：Bearing_CAD + 原版 RoBAS（Windows）

本项目源代码在 Git 中；旧版 RoBAS 模板、SQLite、系数 CSV、SHX 字体以及经过授权的 CADImport DLL **必须放在 Git 仓库外**。不要将原版 DWG、数据库、DLL 或 SHX 复制进公开仓库。

## 1. 推荐目录

```text
D:\Bearing CAD\
├── Bearing_CAD\                         # Git 仓库，python + Vite + C# bridge 源码
│   ├── bearing_cad\
│   ├── bridge\cadimport\
│   │   └── bin\Release\CadImportBridge.exe   # 本机编译的输出，Git 忽略
│   ├── config\robas.local.json          # 本地绝对路径配置，Git 忽略
│   ├── scripts\
│   └── dist\                            # npm run build 的输出，Git 忽略
├── RoBAS_Resources\                     # RoBAS_Resources.zip 解压所得整个目录
│   ├── Data\
│   │   ├── DGBData.db
│   │   ├── ACBData.db
│   │   └── CRBData.db
│   └── Resource\
│       ├── BallDB.csv
│       ├── CylinderRollerDB.csv
│       ├── CylinderRollerDiameterDB.csv
│       ├── 球轴承零件相关系数.csv
│       ├── 圆柱滚子轴承相关系数.csv
│       ├── 哑图\
│       │   ├── 深沟球DWG\
│       │   ├── 角接触DWG\
│       │   └── 单列圆柱DWG\
│       └── shx\
│           └── hztxt.shx                # AutoCAD 字体文件在这里
├── RoBAS_Licensed\
│   └── CADImport.dll                     # 合法授权文件，仅在本机保留
└── RoBAS_Legacy\                        # 可选，仅用于原版源码审查
    ├── RoBAS.zip
    ├── CADLib.zip
    ├── CSharpLib.zip
    ├── EyeShotPlotLib.zip
    └── 其他合法持有的旧版依赖包
```

注意：`RoBAS_Resources.zip` 已经包含最外层 `RoBAS_Resources/` 文件夹，解压时不要形成双层 `RoBAS_Resources\RoBAS_Resources\Data`。压缩包中的多份 MDB / 参考 PDF 可以保留原样，不需要手工删减。旧 Eyeshot DLL 是原版 C# 软件依赖，不是当前 Python/CadQuery 生成三维模型的运行时依赖。

## 2. 一次性安装资源

在 PowerShell 中执行（把两个输入文件路径改成你存放 ZIP 和已授权 DLL 的位置）：

```powershell
cd "D:\Bearing CAD\Bearing_CAD"
powershell -ExecutionPolicy Bypass -File .\scripts\install_robas_resources.ps1 `
  -ArchivePath "D:\Downloads\RoBAS_Resources.zip" `
  -CadImportDllPath "D:\Downloads\CADImport.dll"
```

脚本会把资源解压到同级 `RoBAS_Resources\`，把授权 DLL 复制到 `RoBAS_Licensed\`，并生成不会提交到 Git 的 `config\robas.local.json`。如果资源已存在，脚本拒绝覆盖，防止破坏已经配置好的原版模板。用户也可手工放置资源，并复制 `config\robas.local.example.json` 改成以上本机路径。

## 3. 构建并启动

```powershell
cd "D:\Bearing CAD\Bearing_CAD"
conda activate bearing-cad02
npm ci
npm run build
powershell -ExecutionPolicy Bypass -File .\scripts\run_bearing_cad_with_robas.ps1
```

启动脚本从 `config\robas.local.json` 读取 `resources_path` 和 `cadimport_dll_path`；在 Windows 上执行资源预检、编译 C# CADImport 桥接器，并用 `--robas-resources` 与 `--cadimport-bridge` 启动本地 CAD API。

浏览器打开：http://127.0.0.1:8090/rolling.html

如果 .NET Framework 4.5.2 Developer Pack、MSBuild 或合法 CADImport 授权缺失，二维出图会失败；三维 Python/OCCT 构建与之独立。

## 4. AutoCAD HZTXT.SHX

本次资源包已包含 `Resource\shx\hztxt.shx`。在 AutoCAD 的 `OPTIONS → 文件 → 支持文件搜索路径` 添加：

```text
D:\Bearing CAD\RoBAS_Resources\Resource\shx
```

然后重新打开生成的 DXF。不要把原始 SHX 字体自动替换成不明字体，也不要提交字体文件进 Git。

## 5. 二维图纸的工程验收边界

- 深沟球、角接触球、N 型圆柱滚子的原始模板组合由 `FrmMain.cs` 直接明确使用。
- NU/NJ/NF/NUP 的相应 DWG 文件在提供的 RoBAS 资源包中真实存在，但原始 `FrmMain.cs` 没有为它们提供与 N 一样的四张图组合入口。
- 新增的 NU/NJ/NF/NUP 组合包含与其他构型共用的模板文件；其 `template_composition_review` 标记为 `INFERRED_SOURCE_FILES_AUTOCAD_REVIEW_REQUIRED`。**必须由用户在授权 Windows CADImport 导出后，使用 AutoCAD 检查总图、各零件图、活动挡圈图、字体及标注，才能称为原版正确出图。**
- NUP 会额外生成 `loose_rib.dxf` 和对应 SVG 预览；不能把第五张图静默丢弃。
- 不增加 2D/3D 几何等价门禁，也不修改原始 DWG 线条或 CADImport 精确 TEXT 替换算法。

## 6. 阶段交付和未覆盖范围

- 沟曲率：DGB 0.51/0.53；ACB 0.515/0.525，依据 RoBAS 几何源码调用路径自动计算。
- 钢球数量：DGB 186° 经验式；ACB 依据保持架材料的 `CalcuBallNum`。这是几何初值，不代表完整 RoBAS 最优设计。
- 圆柱滚子：保留原版直圆柱模式；倒角、凸度是可切换的 Bearing_CAD CAD 增强，不冒称来源于原版。
- 完整 RoBAS Optimizer、承载寿命/刚度、外部 `RoBAS_v2.exe` 和多 Agent 计算接入均留待后续单独迁移。

## 7. 本地回归命令

建议在修改后运行（如当前 conda 环境没有 pytest，按 `environment-v2.yml` 安装该测试依赖）：

```powershell
python -m pytest tests_v2 -q
node --test rolling_manifest.test.js rolling_robas_geometry.test.js
npm run build
npx playwright test
```

测试里的 Linux/DXF mock 验证不能代替 CADImport 的授权 Windows 运行；对 NU、NJ、NF、NUP 的最终工程图，必须使用真实 DWG/DXF 加 AutoCAD 检查。
