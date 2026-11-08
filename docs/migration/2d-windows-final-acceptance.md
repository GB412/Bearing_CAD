# PR-2D-09 · Windows 原版 CADImport + AutoCAD 整体验收

## 本 PR 的目标和边界

本 PR 增加可在 Windows 受授权环境里使用的只读验收留证工具，配合真实 DWG→CADImport→DXF/SVG 出图和 AutoCAD 人工审查。工具**不会自动调用商业 DLL 或 AutoCAD**，也不能证明 Windows 实机出图已经成功。

不修改原版 DWG、SQLite、CSV、SHX、CADImport 桥接器，也不修改三维 OCC/STEP/STL，不编造公差与工程值。Manifest 的 manufacturing_approved 必须继续为 false。GitHub Linux CI 不等于 Windows CADImport/AutoCAD 验收。

## 一、在本机真实生成新 DXF

建议从现有主仓库创建独立 worktree，避免污染未提交文件；路径仅为历史示例。

~~~powershell
cd "D:\RotorStudio\Bearing_CAD\Bearing_CAD"
git fetch origin
git worktree add --detach "..\Bearing_CAD_PR87" origin/feat/2d-robas-windows-acceptance-evidence
cd "..\Bearing_CAD_PR87"

# 仅在原配置存在且路径有效时复制，本地配置应保持 Git 忽略。
Copy-Item "..\Bearing_CAD\config\robas.local.json" "config\robas.local.json"

conda activate bearing-cad02
python -m pytest tests_v2/test_drawing_acceptance.py -q
python -m pytest tests_v2 -q
npm ci
npm run build
.\scripts\run_bearing_cad_with_robas.ps1
~~~

访问 http://127.0.0.1:8090/rolling.html，分别输入有效设计参数，真实点击生成二维图纸；DXF 和 SVG 均须由这次运行产生，不能把之前的旧缓存当作测试结果。

~~~powershell
git rev-parse HEAD
Get-ChildItem ".\artifacts" -Filter drawing_manifest.json -Recurse |
  Select-Object FullName
~~~

记录每个真实输出的 bundle_key、request_hash、出图日期、实际输入、CADImport 版本和日志。单靠 git HEAD 不能证明旧文件来自当前运行，故需保留新 worktree 的输出路径与本次操作记录。授权 DLL、DWG/SQLite/CSV 和 SHX 不得上传公开 GitHub。

## 二、代表性实际验收案例

| 类型和构型 | 张数 | 重点 |
|---|---:|---|
| DGB 6008/P5，40×68×15 mm，系列 0 | 4 | 原版 BearingType.db 核实型号；40/68/15 + 6208/P5 应阻断 |
| ACB：经本机设计验证的代表样例 | 4 | 角接触沟道、锁口/保持架、技术条件 |
| CRB N：经本机设计验证的代表样例 | 4 | 原版 FrmMain 明确支持的 N 模板 |
| CRB NU | 4 | 需人工核实非 N 模板推断 |
| CRB NJ | 4 | 需人工核实非 N 模板推断 |
| CRB NF | 4 | 需人工核实非 N 模板推断 |
| CRB NUP | 5 | 必须有 loose_rib.dxf / loose_rib.svg，且单独审图 |

ACB 和 CRB 参数须来源于实际可生成的有效设计，不为补充测试数量杜撰型号或工程尺寸。标准表边界和 getter 精度已在前述 PR 的单元测试中覆盖，不能代替真实 CAD 图纸。

## 三、离线自动审计命令与输出

使用 Python 命令，将每个案例和真实 bundle 文件夹按 LABEL=PATH 绑定。以下为需要替换成实际路径的**示例**：

~~~powershell
$cases = @(
  "--case", "DGB6008=D:\实际目录\drawings\DGB-bundle-key",
  "--case", "ACB=D:\实际目录\drawings\ACB-bundle-key",
  "--case", "CRB_N=D:\实际目录\drawings\N-bundle-key",
  "--case", "CRB_NUP=D:\实际目录\drawings\NUP-bundle-key"
)
python -m bearing_cad.drawing_acceptance @cases --out "D:\RoBAS-Review\PR87-acceptance"
~~~

可以先提交部分案例；报告会列出没有覆盖的其他构型。补齐 NU/NJ/NF 后应使用新的输出目录重新审计。已有输出目录不允许覆盖。源 DXF、Manifest 均只读，不修改源资源。

工具会检查真实文件大小及 SHA256、NUP 五图顺序、ezdxf 实体解析/致命错误，提取每张 DXF 的 TEXT/MTEXT/其他实体数量和 SHX 字体引用，记录原版模板文件名与哈希、CADImport 报告的匹配次数、实际命中变量的拟填值及来源、命中空项、重复来源歧义、未映射占位符、型号与标准表告警。

旧 Manifest 缺少 PR-2D-08 来源诊断、图纸文件被篡改或不含合法文件摘要时，明确标为自动审计失败。字体引用只能说明 DXF 所用样式，**不能保证 AutoCAD 中文字体显示正确**。

本机输出四份不会覆盖的结果：

- acceptance_report.json：机器可读的完整证据索引；
- acceptance_report.md：各案例的自动检查与构型覆盖汇总；
- autocad_review_checklist.md：逐张图纸默认为“待审”的人工核查清单；
- defects_template.csv：空白缺陷分类表。

这些文件不自动上传仓库，不复制原始 DWG/SQLite/CSV、SHX、CADImport DLL。

## 四、AutoCAD 必须人工核对

在 AutoCAD 中打开每个本次生成的 DXF。按 docs/robas-local-deployment.md 配置 HZTXT.SHX 支持字体路径。逐张核实图框/线型/比例、中文与 SHX 显示、尺寸/上下偏差、游隙、粗糙度、技术条件、型号和 d/D/B、保持架、残留占位文字、缺来源的重量字段以及 NUP 活动挡圈独立图。

实际缺陷严格分成：**SOURCE_CALCULATION / FIELD_APPLICABILITY / CADIMPORT_TEXT_REPLACEMENT / ORIGINAL_DWG_TEMPLATE / SVG_PREVIEW_ONLY**。源码和 DB 问题与字体仅预览问题不得混为一谈。若查明确实存在代码 bug，先提交审核材料，再由用户批准最小修复 PR；无源工程数据不能凭空填值。

## 五、状态区分和结束条件

| 状态 | PR-2D-09 的真实能力 |
|---|---|
| CODE_IMPLEMENTED | 自动审计工具、测试与文档 |
| CI_PASSED | 以 PR 最新 HEAD 的 GitHub CI 为准 |
| WINDOWS_CADIMPORT_VERIFIED | 尚未证实，须用户 Windows 真实出图、保存日志 |
| AUTOCAD_REVIEWED | 尚未证实，须实际打开每张图并提供截图/审图人记录 |
| MANUFACTURING_APPROVED | 否，需专业工程审核独立判定 |

完整迁移应达到：当前支持模板中有可靠原版来源的有效字段正确填充，缺失项可见，型号和设计参数一致，七类真实 DXF/AutoCAD 验收通过且遗留事项记录完备。并非全部 SQLite 变量必须无条件非空，也不能由 CI 自动宣称制造批准。
