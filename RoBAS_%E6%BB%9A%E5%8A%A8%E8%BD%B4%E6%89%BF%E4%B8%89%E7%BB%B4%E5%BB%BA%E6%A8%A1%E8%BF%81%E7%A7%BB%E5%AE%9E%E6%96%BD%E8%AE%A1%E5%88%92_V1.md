# RoBAS 滚动轴承三维建模迁移至 Bearing_CAD：实施计划 V1.0

**编制基线**：2026-10-26，`GB412/Bearing_CAD` main `291574459990a854d88fe5aefcf561810105f2ad`（PR #5 已合并）；参考材料 `/mnt/data/RoBAS.zip`，文件共 188 项，其中 `.cs` 101 项。

**一句话目标**：参考 RoBAS 的深沟球、角接触球和圆柱滚子轴承三维几何构造方法，在现有 Python CadQuery/OCCT 中实现可校验 B-Rep 和 STEP 装配，并接入现有 Three.js 工作台，同时保证滑动轴承功能不回归。

> 本文件是实施规格和验收契约，不代表任何 PR 已实施，不代表新滚动轴承满足承载、寿命、公差或 GB/ISO 制造认证。RoBAS 参考源码在未确认授权前只在私有开发环境使用，不入公共仓库。

## 0. 项目边界与已验证事实

### 0.1 已有基础资产

- `cad02_pipeline.py`：CadQuery/OCCT B-Rep、STEP/STL、HLR、DXF/SVG、几何哈希及 manifest、DRAFT 约束；**当前只支持** `housing/bushing/shaft`。
- `cad_workbench_drawing.py`：滑动轴承实际半剖实体、剖面线和尺寸复核图；保留，不直接用于滚道生成。
- `cad03_server.py`：本机同源服务、输入检查、成果查询下载；目前单一滑动轴承模型。
- `viewer.js`：Three.js 相机、STLLoader、交互和爆炸功能；装配零件名与数量写死。
- `tests/test_cad02.py`、`tests/test_workbench.py`、`tests-browser/cad01.spec.js`：已有回归测试；新流程必须持续运行。
- `.github/workflows/workbench.yml`：仅匹配特定分支及 PR，**未配置 push: main**，需补 main 回归门禁。main 已有的 CAD-01、CAD-02、CAD-03 CI 成功不应被误称为工作台 CI 必定覆盖 main。
- `README.md`、`IMPLEMENTATION_PLAN.md`：旧阶段的文档，新迁移 PR 应建立清晰的权威文档并逐步修订旧入口，避免把滑动轴承和滚动轴承混淆。

### 0.2 明确不做

不迁移 WinForms/Eyeshot GUI、DWG 模板换字、RoBAS 寿命与动力学分析、优化器/标准选型、V3.1 LangGraph/候选用户确认。滚动轴承三维先验收后，二维工程图属于**可选独立项目**；不阻断三维 MVP。

### 0.3 技术路线

- 建模：Python 3.11 + CadQuery 2.5.x + OCCT (conda-forge)。以参数化 B-Rep 作为唯一几何真源。
- 浏览器：Three.js 根据后端**动态零件 manifest** 加载由 B-Rep 导出的 STL；不是 Three.js 仿造精确实体。
- API：`bearing_type` 识别插件，后端可信校验，不接受 `CONFIRMED`、`confirmed_by` 等用户权限伪造信息。保留 `/api/cad02/generate` 的旧滑动轴承兼容接口；新建版本化统一入口。
- 标准单位：**mm**。模型 Z 轴为轴承中心轴，轴向原点为轴承中面；节圆位于 XY 平面；角度在 JSON 为 `*_deg`，内部计算转弧度。
- 精度：尺寸公差按相应几何功能设定，不把 `0.001 mm` 显示位数误当实体布尔容差；避免把理论接触边界上的数值交差误报成几何碰撞。

## 1. RoBAS 源文件迁移地图（以压缩包真实路径为准）

| RoBAS 文件（均相对 `RoBAS/`） | 有效内容 | 新实现位置 | 风险 |
|---|---|---|---|
| `Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs` | 深沟球轴承默认值、尺寸派生、滚道曲率 | `bearing_cad/rolling/deep_groove.py` | 旧算法部分单位不一致；默认值与构造值不完全一致 |
| `Core/BallBearing/DeepGroveBallBearing/DeepGrooveBallBearing.cs` | 组装内外圈、滚动体、保持架 | `bearing_cad/rolling/deep_groove.py` | 一处节圆公式使用 `0.5*(d+d)`，须隔离疑似缺陷 |
| `BearingModel/Race/InnerRace/SingleRowDeepGrooveInnerRace.cs` | 圆柱壳体减环面滚道 | `rolling/races.py` | 接触/相切 B-Rep 容差、壁厚 |
| `BearingModel/Race/OuterRace/SingleRowDeepGrooveOuterRace.cs` | 外圈壳体减环面滚道 | `rolling/races.py` | 径向游隙单位及滚道接触关系 |
| `BearingModel/Roller/BallRoller.cs` | 节圆阵列 `2πi/Z` | `rolling/elements.py` | 数量与重合、拼装中心位置 |
| `BearingModel/Cage/SpherePocketCage.cs` | 环形笼体球兜布尔切除 | `rolling/cages.py` | 初始球兜在 `<= pocketNum` 循环前后重复切除 |
| `BearingModel/Cage/StampingCage.cs` | 冲压保持架、球窝、铆钉相关生成 | `rolling/cages_stamped.py` | 多段布尔/多零件，优先后置 |
| `Core/BallBearing/AngularContactBallBearing/ACBGeometry.cs` | 接触角与不对称滚道参数 | `rolling/angular_contact.py` | `cos(alpha)`/`sin(alpha)` 的 alpha 约定必须复核 |
| `BearingModel/Race/InnerRace/SingleRowAngularContactInnerRace.cs` | 内圈侧肩、锥/环面布尔 | `rolling/angular_contact.py` | 圆台与沟道相交，拓扑容易失效 |
| `BearingModel/Race/OuterRace/SingleRowAngularContactOuterRace.cs` | 外圈侧肩、锥/环面布尔 | `rolling/angular_contact.py` | 同上 |
| `Core/RollerBearing/CylinderRollerBreaing/CRBGeometry.cs` | 圆柱滚子与挡边构型参数 | `rolling/cylindrical_roller.py` | N/NU/NJ/NUP/NF 结构区别；`Breaing` 原拼写 |
| `Core/RollerBearing/CylinderRollerBreaing/CylinderRollerBearing.cs` | 五种构型开关及零件组合 | `rolling/cylindrical_roller.py` | 不能把 NUP 错当完全等同固定双挡边 |
| `BearingModel/Race/InnerRace/SingleRowCylinderInnerRace.cs` | 内圈无/单/双挡边造型 | `rolling/races.py` | 挡边倒角和端面几何 |
| `BearingModel/Race/OuterRace/SingleRowCylinderOuterRace.cs` | 外圈无/单/双挡边造型 | `rolling/races.py` | 同上 |
| `BearingModel/Roller/CylinderRoller.cs` | 圆柱滚子节圆阵列 | `rolling/elements.py` | 端部轮廓、轴向居中 |
| `BearingModel/Cage/CylinderPocketCage.cs` / `StraightPocketCage.cs` | 柱状滚子保持架及窗孔 | `rolling/cages.py` | 孔/窗布尔切除；滚子—保持架间隙 |

**基准值**：DGBGeometry 默认外径 180 mm、孔径 100 mm、圈宽 30 mm、钢球直径 19.05 mm、节圆直径 140 mm、钢球数 18。该组数值用于“源码解析/对照基线”，**不等于结构已经通过工程验算**。其默认保持架宽度 36.241 mm 大于圈宽，必须被识别为待审输入或作为专门的源码重现用例，不可悄悄标准化。

**关键分歧**：`DeepGrooveBallBearing.cs` 一处显式构造函数写 `Dpw=0.5*(d+d)`，而 `DGBGeometry.cs` 写 `0.5*(outsideDia+insideDia)`；应记录源算法 A/B 与受审核的新规则，禁止将可疑表达式直接翻译为 Python。`SpherePocketCage` 对球兜先减一次，再 `i<=pocketNum` 循环；重实现以 `0 <= i < Z` 每个球兜切除恰一次。

## 2. 目标架构（小步演进）

```text
Bearing_CAD/
  bearing_cad/
    contracts.py                # CadRequest, PartRecord, AssemblyResult, ArtifactManifest
    registry.py                 # bearing_type → geometry builder
    geometry/
      validation.py             # OCCT 单件体积、有效性、尺寸、接触/干涉
      exports.py                # 复用并抽取 STEP/STL/文件 hash
    rolling/
      races.py                  # 轴承圈的 B-Rep 基本构造/沟道
      elements.py               # 钢球/圆柱滚子阵列
      cages.py                  # 球兜/圆柱兜保持架
      cages_stamped.py          # 复杂冲压保持架（后置）
      deep_groove.py
      angular_contact.py
      cylindrical_roller.py
  fixtures/rolling/
    ro_baseline_deep_groove.json
    valid_deep_groove.json
    angular_contact_*.json
    cylindrical_*.json
  docs/rolling_migration/
    source_map.md
    unit_formula_audit.md
    acceptance_matrix.md
    handoff_status.json
  ...现有 cad02_pipeline.py、cad_workbench_drawing.py、cad03_server.py、viewer.js 逐步适配...
```

### 2.1 最小公共契约

请求示例（是接口草案，非工程合格尺寸）：

```json
{
  "schema_version": "bearingcad.request.v1",
  "bearing_type": "rolling.deep_groove_ball",
  "unit": "mm",
  "parameters": {
    "bore_d_mm": 100,
    "outside_d_mm": 180,
    "width_mm": 30,
    "pitch_d_mm": 140,
    "ball_d_mm": 19.05,
    "ball_count": 18,
    "inner_groove_curvature": 0.52,
    "outer_groove_curvature": 0.54,
    "cage_kind": "sphere_pocket"
  }
}
```

- `bearing_type` 初期支持 `plain.journal_cylindrical`、`rolling.deep_groove_ball`，再依次开放 `rolling.angular_contact_ball` 和 `rolling.cylindrical_roller`。
- `PartRecord`：`part_id`（稳定唯一 ID）、`category`、`role`、`display_name`、`color`、`transform`、`BRep shape`（仅内存）、`exported_files`、`material_hint`（可选）。每个钢球一个实例：`ball_001...ball_Z`，保持架可多零件。
- `AssemblyResult`：轴承类型、零件列表、几何校验报告、输入规范化参数、导出提示；**不包含可写的用户确认字段**。
- `ArtifactManifest`：`schema_version`、`bearing_type`、`generator_version`、`geometry_hash`、`part_manifest[]`、`file_sha256`、`approval_state:DRAFT`、`unit:mm`、拓扑/接触测试结果。`geometry_hash` 必须包含类型、规范化输入、构型版本与内核/生成器版本。
- 使用后端零件清单作为权威对象映射，前端不再根据三个固定数组位置推测模型名称。
- CadQuery 模型的几何坐标约定：轴线 Z，宽度居中 Z=0，滚动体中心 XY 平面。角接触球若存在轴向偏置，必须在参数模型与 manifest 显式记录。

### 2.2 关键实现选择

- 沟道必须是精确圆弧/环面 B-Rep：采用 OCCT 旋转扫掠或可控环面布尔，不允许退化为矩形环槽，也不能直接拿 STL 参与布尔。
- 装配 STEP 包含独立圈体/钢球/保持架，可被 FreeCAD 回读和辨认；STL 每零件导出用于 Web 展示。
- 同轴及滚动体等角位置按解析参数先做数值测试，再做 B-Rep 求交；在名义接触处使用明确的容差分层，并报告允许接触、预期间隙和意外体积干涉。
- 执行器只传结构化输入。不得读取/信任前端自称 `approved` 或 `confirmed_by` 的值。
- 资产存储独立于会话，使用参数哈希索引；同参数重复调用无需重新建模，参数不同不得误复用。

## 3. PR 任务链及独立验收

约定：当前 PR 已到 #5；以下使用 **MIG-01～MIG-09 逻辑编号**，GitHub PR 数字创建时自增，避免依赖未来真实编号。每个 PR 可独立 review / revert；下一个仅从上一个已经合并且 CI 全绿的 main 创建。

### MIG-01：迁移基线和自动化门禁（第一个 PR）

**工作**：
1. 检查当前 main 全部已有 CI；补充 `workbench.yml` 的 main push 门禁。增加滚动轴承专用 `rolling-cad.yml`，以 conda-forge Pin CadQuery/OCP 和 Python/Node，初期运行空/契约测试而非伪造功能测试。
2. 建立 `docs/rolling_migration/source_map.md`（源码行/方法→参数→新目标）、`unit_formula_audit.md`（原始单位、公式歧义、保留/拒绝原因）、`acceptance_matrix.md`。
3. 引入最小 `CadRequest`, `PartRecord`, `AssemblyResult` dataclass/pydantic 数据契约和动态装配基本校验，不改原浏览器主逻辑；旧滑动请求保留。
4. 将 RoBAS 默认参数以**手工核查的小型 JSON fixtures**保存；不要提交未授权的 ZIP/C#/Eyeshot DLL/DWG。
5. 在项目根目录新增简短 `AGENTS.md` 指示跨轴承边界、CI、审查和权限限制；为后续 PR 准备单一有序的 `docs/rolling_migration/handoff_status.json`。

**验收**：旧四套 Python/JS/Playwright 回归绿；rolling 契约测试对伪造确认、错误类型、单位冲突报错；main 的完整几何 CI 被触发；源映射有文件路径、公式、单位和风险。**不允许此 PR 直接创建滚动轴承三维模型**。

### MIG-02：深沟球轴承两个轴承圈和钢球（第一套可见成果）

**工作**：`rolling/races.py` 真正的内外圈、`rolling/elements.py` 钢球实体 + 节圆等角阵列，`rolling/deep_groove.py` 用参数组合成无保持架装配。

**验收**：用 RoBAS 默认基线 100/180/30、19.05、PCD 140、18 球，并加至少 2 组工程几何可行数据；内外圈尺寸/沟道半径和位置的数值断言；球数 Z、中心半径 PCD/2、角度间距 360/Z；每个 B-Rep 实体非空、拓扑有效、单独 STEP 可回读；无“全部球合并成一个不可拆分实体”的退化。完成后产出 STEP（可回读）与三维基准图片/几何报告。

**风险**：旧 RoBAS 默认/参数计算不一致导致干涉——明确报错或记录差异，不得为了“测试变绿”静默修改 fixture 期待值。

### MIG-03：深沟球轴承保持架及完整装配

**工作**：基于 `SpherePocketCage.cs` 的环形球兜保持架，布尔减去 Z 个兜孔（每个恰一次）、记录球兜径向/轴向间隙；优先一个完整实体；复杂冲压保持架另开阶段。把球/内圈/外圈/笼体作为独立零件。

**验收**：含一个保持架的简单构型应有 Z+3 个零件；零件互不误融合；兜孔总数 Z；球兜轴向对称、无不合理体积重叠；完整 STEP 装配回读可辨识圈/球/保持架；不满足输入时明确拒绝。针对 RoBAS 保持架默认宽度不合理的用例应有明确警告或拒绝策略。

### MIG-04：公共导出和服务适配（保留滑动轴承）

**工作**：抽取 STEP/STL、B-Rep 校验、manifest/hash 作为面向任意 PartRecord 的公共接口，建立 `bearing_type` 路由；旧 `/api/cad02/generate` 滑动接口与旧 artifact 命名继续兼容，新增 `/api/v1/cad/generate` 和 `.../artifacts` 或等价版本化接口。为滚动轴承提供完整元素文件清单；不得把所有球硬编码为 `ball_01..ball_18` 固定数量。

**验收**：同一 API 根据 `bearing_type` 分别生成滑动轴承三件装配与深沟球轴承 Z+3 装配；输入无效返回 422；旧客户端零改动仍可使用；manifest 中每个零件文件的 hash 一致；SHA 破坏拒绝复用；不同类型相同基础尺寸哈希不冲突。

### MIG-05：统一 Web 三维查看及滚动轴承交互

**工作**：类型选择滑动/深沟球；滚动参数区（D/d/B/Dw/PCD/Z/沟曲率/笼型）；`viewer.js` 改为以 `part_manifest[]` 动态加载、管理材质/可见性、展开零件树、按类别爆炸、聚焦、重置；保留滑动半剖模式与复核图；切换类型与修改参数后取消旧请求、清空失效文件，不允许 stale STL 覆盖新模型。

**验收**：Playwright 生产构建真实后端 E2E，从页面生成 18 球 + 2 圈 + 1 笼的 STL 并能分别显隐；截图/三维检查；两种类型互切不串结果；滑动既有二维/半剖回归通过；视图控制不依赖零件顺序。脚本与 CI 能提供可下载截图、STEP、manifest 作为无人值守证据。

### MIG-06：角接触球轴承 3D

**工作**：核对 `ACBGeometry.cs` 的曲率、沟道轴向偏置及接触角单位；建立 `contact_angle_deg` 到 rad 的明确转换；重实现非对称内外圈沟道/锥形侧肩、钢球节圆及适配球兜保持架。

**验收**：至少 3 个典型角度（例如 15°/25°/40°，是否几何可行由有效 fixture 决定），角度变化时沟道位置与几何体积发生预期变化；左右圈非对称；球心与沟道参数满足几何关系，STEP 完整回读；负角、过大角、无效间隙等输入拒绝。若参照源码存在角度定义不一致，则先填公式审计报告再实现。

### MIG-07：圆柱滚子轴承主体与 N/NU/NJ/NF/NUP 构型

**工作**：实现内圈/外圈无、单、双挡边；柱状滚子 Z 阵列；基于 `CylinderRollerBearing.Plot3DModel` 显式映射挡边组合；将 NUP 可能涉及的独立挡圈与原代码模型简化区别记录清楚，必要时实现独立构件，不得误标。

**验收**：五种构型各有 fixture + 边界案例；自动检查指定端挡边的数量和几何位置、内/外圈零件独立、柱状滚子总数和尺寸及间距；每个构型 STEP 可回读、无意外穿透，失败输入有诊断；当前前端可选择构型并生成。

### MIG-08：滚动轴承保持架进阶、性能与交互完善

**工作**：`CylinderPocketCage`、`StraightPocketCage`、`StampingCage` 分开实施和测试，优先常用且明确的实际几何构型；不要因为 RoBAS 有 23 KB 的 `StampingCage.cs` 就整体无审查翻译。对极端 Z 与球/滚子尺寸做布尔稳定性保护。优化阵列生成、缓存和浏览器 STL 加载（合理共享几何或分块加载，不牺牲独立零件 ID）。

**验收**：各支持的 cage_kind 都有独立结构断言；球兜/滚子窗孔数量、支撑截面有效、孔洞实际存在；大 Z 测例的资源上限和超时阈值可测；错误参数不导致死循环或无限自修复；必要时对未实现笼型返回 `NOT_SUPPORTED`，不得用错误近似悄悄降级。

### MIG-09：整体验收与可发布三维模块

**工作**：三类轴承统一 end-to-end 回归矩阵；STEP 导入抽检、STL/STEP 坐标一致、part manifest、输出哈希、异常恢复、断网本地服务、构建包及文档。跑生产 Web E2E、进行用户视觉验收样本截图。更新 README，所有旧文档标记历史状态。提供不依赖 RoBAS 原始 ZIP 的可复现 fixture/test 环境。

**验收**：三类核心轴承能真实生成、Web 查看、下载 STEP/STL；PR-05 的滑动半剖及 2D 复核功能不退化；CI 全绿且有独立测试证据；错误情形均可定位；CAD 产物保留 DRAFT 标记。真正制造图、专业性能公式和标准设计未在本阶段完成，单列后续工作。

### PR 依赖与阶段里程碑

- MIG-01 → MIG-02 → MIG-03：**M1 = 深沟球精确三维完整装配可 STEP 导出**。
- MIG-03 → MIG-04 → MIG-05：**M2 = Web 同时支持滑动与深沟球**。
- MIG-05 → MIG-06 → MIG-07 → MIG-08 → MIG-09：**M3 = 三种 RoBAS 滚动轴承三维能力移植并具备自动回归**。
- 每 PR 的 GitHub 序号由平台创建，**MIG ID 是稳定任务 ID**，避免误把旧 PR #5 当作新的模型开发。

## 4. 每个 PR 必须附的证据包（Codex 自动生成）

PR 描述中要包含：

1. 本 PR 的 MIG ID、范围/非目标、RoBAS 对应方法、分支与 base SHA。
2. changed-files、输入参数 fixture ID、生成器版本、关键公式审计结论。
3. 测试命令与真实退出码；CI URL；不得宣称 `skipped` 是通过。
4. STEP/STL 导出清单、各零件数量、体积、BoundingBox、isValid、接触/干涉报告。
5. 关键截图（Playwright 或 FreeCAD 脚本截图）和至少一个可下载 STEP 作为工作流 artifact（不提交大文件进 git）。
6. 自审结果、独立审查提出的问题及对应修复提交 SHA。
7. 剩余非阻断风险和下一个 MIG 的输入条件。

自动门禁（必须机械执行）：

- `npm ci && npm run build && npm run test:unit:js`。
- `python -m unittest discover -s tests -p 'test_cad.py' -v`（Linux shell；PowerShell 按平台调整）。
- `python -m unittest discover -s tests -p 'test_cad02.py' -v`。
- `python -m unittest discover -s tests -p 'test_cad03.py' -v`。
- `python -m unittest discover -s tests -p 'test_workbench.py' -v`。
- 滚动轴承专用 pytest/unittest（拒绝失败/跳过冒充成功）。
- `npm run test:browser`，覆盖旧滑动主流程；新浏览器流程 E2E。
- 尽可能用 `gh api`/GitHub Actions 收集实际产物，不要通过截图替代数值几何验证。

缺少 CadQuery 时**禁止**将真实几何测试自动标记为 skipped 后放行 PR。

## 5. 如何让 Codex 连续执行直至完成（工程上可落地的方式）

### 5.1 不要指望一个 Plan 模式对话自己永久运行

Plan 模式用于拆任务，并不是可靠持久任务调度器。普通 ChatGPT 回合不会因为写了“持续工作”就自行不间断工作。要做到连续推进，需要外部**持久控制器 + GitHub PR/CI 作为状态机**。选择方案：

- **推荐 A（高自动化）**：在专用持续运行的开发环境（自管 runner/工作站）中部署 Codex CLI/SDK 任务控制器。控制器从 `docs/rolling_migration/plan.yaml` 取待办 MIG、启动有边界的 Codex 执行、等待 CI、调 Codex 独立审查、失败反馈重试、绿灯后进入下一个 MIG。开发者仅在风险门禁或阻断原因处介入。控制器需进程托管、GitHub 访问与 API 授权、工作目录隔离、成本和时间上限。不要给它本机全盘或私人凭据的无约束写权限。
- **备选 B（少维护）**：Codex Cloud 每次一项 PR + GitHub Actions 验收，再由外部 GitHub Actions `workflow_dispatch` 或 `repository_dispatch` 状态管理触发下一项。每次 run 是有限时长，不能把一个 GitHub job 写成无限循环。必须做权限隔离、防循环、分支互斥、失败重试上限和审计日志。

`codex exec` 适合单个有限任务；Codex SDK 支持程序控制任务生命周期。官方参考：
- https://developers.openai.com/blog/codex-as-a-platform
- https://developers.openai.com/cookbook/examples/codex/autofix-github-actions
- https://developers.openai.com/blog/custom-code-review-rules-for-codex

### 5.2 控制器状态机

```text
QUEUED
  → PREFLIGHT（main 干净，引用源可访问，依赖版本锁定）
  → IMPLEMENTING（Codex 修改当前 MIG 的范围）
  → SELF_TEST（本地单测、几何测试、生成成果）
  → SELF_REVIEW（仅可读检查 diff，审阅同类错误和未测路径）
  → PR_OPEN（创建草稿 PR，上传证据）
  → CI_WAIT（GitHub 门禁运行）
  ├─ FAILURE → FIXING → SELF_TEST/CI_WAIT（最多 3 次，避免无限循环）
  └─ GREEN → INDEPENDENT_REVIEW
       ├─ P0/P1 → FIXING（最多 2 次）
       ├─ HUMAN_GATE → NEEDS_APPROVAL（结构/授权/算法歧义）
       └─ PASS → READY_TO_MERGE → MERGE（仅允许的 PR 类别）
               → VERIFY_MAIN → NEXT_MIG
```

建议先启用 `GREEN → READY_TO_MERGE`，**不自动合并**。连续跑通前两次 PR 后，才对文档/测试/纯结构辅助类 PR 设置自动合并；对滚道建模规则、授权、可疑公式、标准符合性、已知实体穿透等设置人工审核或指定评审者审批。自动推进不是绕过领域责任。

### 5.3 精简机器规则

- `AGENTS.md`：3 类硬约束：不用未经验证的 RoBAS 公式、滑动功能不得回归、任何 3D 模型须真 B-Rep 验证。
- `plan.yaml`：MIG ID、depends_on、allowed_paths、acceptance_commands、requires_human_review、max_attempts。
- `handoff_status.json`（或 GitHub issue 状态）：当前 MIG、PR 号、CI run、最后通过 SHA、阻断原因。GitHub PR 和 CI 是外部事实来源；不能仅相信 Codex 自己说“完成”。
- `docs/rolling_migration/decision_log.md`：每一处从 RoBAS 公式偏离的原因及验证证据。
- **所有自动化只在有限并发**下运行：一个迁移 MIG 同时至多一个写入任务；审查使用独立只读上下文。
- `main` 保护：要求 CAD-01/02/03/Workbench/Rolling 相关工作流、至少年审查规则（按仓库支持）、禁止强推、PR 合并、更新分支后重跑。当前 GitHub 查询没有发现 rulesets；branch protection 因连接器权限无法核实，必须由管理员确认。

### 5.4 停止条件和成果定义

停止并标记 BLOCKED：原始 RoBAS 源码缺失或版权无法确认、公式单位歧义无法验证、CadQuery 布尔不可稳定重现、连续 3 轮 CI 失败、测试必须降级/跳过才能过、产生不可解释装配干涉、CI 超过预算/配额。停止自动合并并请求指定评审人处理。

项目完成 `DONE` 必须满足：MIG-01～09 对应 PR 已合并，main 全部相关 CI 绿，RoBAS 三类轴承代表性模型均有 B-Rep/STEP 回读与 Web 实测证据，滑动轴承旧功能未退化，开源/第三方依赖许可边界清楚，所有限制在 README 显式说明。不能仅以“代码无异常”判定全部完成。

## 6. Codex 总控提示词（一次性放入控制器）

```text
你是 Bearing_CAD 滚动轴承三维迁移执行 Agent。唯一权威实施规格：
docs/rolling_migration/MIGRATION_PLAN.md 和 docs/rolling_migration/plan.yaml。

从最新 main 和当前状态机读取第一个未完成 MIG；先 read-only preflight，
确认 RoBAS 私有源码路径和当前基线，再只实施当前 MIG 的允许变更。
禁止同时开发后续 MIG，禁止修改 V3.1，多 Agent 用户确认状态永不由 CAD 写入。

实施前检查旧的 CAD-01、CAD-02、CAD-03、Workbench 测试；
本 MIG 使用先测试后实现策略。完成后运行所有验收命令，
导出 STEP/STL 与 manifest，检查体积、几何、零件数、接触关系、STEP 回读。
对有歧义的 RoBAS 公式记录为 BLOCKED / NEEDS_REVIEW，不自行编造经验值。

每个 MIG 创建独立分支 PR，附测试命令、CI URL、成果 SHA、源码映射和风险。
检查自审/独立审查问题，最多进行 3 轮 CI 自修复；
超限或影响授权/专业安全时停止并标记 BLOCKED。
所有 status、merged、CI success 必须从 GitHub API 验证，不可信任模型声明。
下一 MIG 必须在此 PR 合并后由控制器开始，不能从未合并的临时分支派生。
完成 9 项 MIG 且 main 全绿时标记 DONE 并形成最终移植验收报告。
```

## 7. 使用 RoBAS.zip 的一次性准备

`/mnt/data/RoBAS.zip` 是**当前对话运行环境**可读取的文件，不等于 Codex 本地目录有这个文件。给 Codex 本地执行时，需用户在开发机提供一个私有可读路径，例如 `D:\\Reference\\RoBAS.zip`；无需也不应自动提交该源码 ZIP 到公开仓库。可在编排器环境变量中设置 `ROBAS_SOURCE_ZIP` 指向此路径；若不存在则 PREFLIGHT BLOCKED。把参考文件的 SHA-256 记录于审计文档，并从根路径按需读取。仓库只保存自己编写的测试 fixtures、公式说明和源码路径索引，不保存 Eyeshot DLL、原 C# 源码或 DWG 模板。

## 8. 工期和验收责任

**不将时间估算写为必须交付承诺**。粗略工作量优先级：MIG-01 小，MIG-02/03 中，MIG-04/05 中，MIG-06/07/08 大（几何歧义多），MIG-09 中。对存在 3D 布尔歧义的类型设置单独评审阶段。

软件自动化能够验证几何与导出行为，不能替代对承载、寿命、公差、接触角、润滑结构、材料与标准的专业审核。专业审核结果作为后续标准/制造认证类项目的输入，与本次 3D 功能迁移里程碑分开管理。
