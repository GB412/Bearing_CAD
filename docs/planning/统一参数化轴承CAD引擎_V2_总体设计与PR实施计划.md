# 统一参数化轴承 CAD 引擎 V2.0：总体设计与 PR 实施计划

> 版本：V2.0（2026-10-26）  
> 定位：面向多 Agent 轴承设计系统，基于 RoBAS 的滚动轴承几何算法，建设可独立验证、可追溯、可扩展的参数化 CAD 子系统。  
> 来源：用户提供 `RoBAS.zip`；现有 GitHub 仓库 `https://github.com/GB412/Bearing_CAD`（已静态审查关键代码）。  
> 状态：技术规划，不代表已执行开发、运行全部测试或获得制造工程图认可。

## 0. 执行摘要（先读）

**决策 D1：不在 AI 生成的旧 Bearing_CAD 上继续堆叠滚动轴承专属逻辑。** 在原 GitHub 仓库创建 V2 隔离开发分支和独立包 `bearing_cad/`；保留旧版工作台作回归参照，V2 达标后逐步迁移而非提前删除旧代码。

**决策 D2：不迁移 WinForms/Eyeshot 软件。** RoBAS 是算法与建模知识来源；三维内核采用 Python + CadQuery + OCCT（必要时使用 OCP 低层接口），浏览器采用 Three.js；独立零件装配导出 STEP，显示网格另行生成。

**决策 D3：几何设计参数与 CAD 构造严格分离。** CAD 不负责载荷、寿命、转速等设计决策，不得擅自覆盖主 Agent 已确认的几何参数；对缺失内部细节允许“显式标记的概念建模策略”，但不伪装成已校核工程设计。

**决策 D4：先三维实体，后二维工程图，再接多 Agent。** 先单列深沟球轴承，后圆柱滚子与角接触球；先内外圈+滚动体，再逐步加入保持架高精度版本；二维图纸基于同一 B-Rep 投影/剖切，制图标准检查另成阶段。

**决策 D5：每个 PR 单独验证。** Codex 每次只开发一个 PR，创建分支、实现、补测试、运行门禁、写自检报告，开 PR；审查通过再进入下一个。不允许 Codex 在失败状态下跳过门禁、直接覆盖 main 或自行认定“工程合格”。

### 项目成功标准

1. 三类滚动轴承按明确参数独立生成内圈、外圈、Z 个滚动体和可配置保持架；零件语义、数量、朝向、位置正确。
2. 模型由确定性 B-Rep 生成；无效几何、严重零件干涉、负壁厚、球体碰撞等输入被阻断或给出可复现诊断。
3. STEP 装配能在至少一种独立 CAD 软件中打开，且语义零件清单与零件数量一致；STEP 精度与显示 STL 三角化质量单独验证。
4. 同一设计输入生成可追溯的 SVG/DXF 图纸（开发早期为“结构复核图”；通过专业审图前不得称“制造图”）。
5. 与多 Agent 候选快照单向集成：草案只能 DRAFT；正式发布状态由可信主系统提供；模型文件严格绑定几何哈希、引擎版本、设计版本。
6. 原滑动轴承旧工作台不因 V2 开发而退化；是否迁移到新引擎在 V2 通过里程碑后决定。

---

## 1. 现有代码基线与评估

### 1.1 RoBAS 的三条建模调用链

| 轴承 | 参数/设计计算入口 | 装配调用入口 | 重要实体实现 |
|---|---|---|---|
| 深沟球 | `Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs` | `DeepGrooveBallBearing.cs::Plot3DModel` | `BearingModel/Race/InnerRace/SingleRowDeepGrooveInnerRace.cs`；`OuterRace/SingleRowDeepGrooveOuterRace.cs`；`Roller/BallRoller.cs`；`Cage/StampingCage.cs` |
| 圆柱滚子 | `Core/RollerBearing/CylinderRollerBreaing/CRBGeometry.cs` | `CylinderRollerBearing.cs::Plot3DModel` | `SingleRowCylinderInnerRace.cs`；`SingleRowCylinderOuterRace.cs`；`CylinderRoller.cs`；`CylinderPocketCage.cs` |
| 角接触球 | `Core/BallBearing/AngularContactBallBearing/ACBGeometry.cs` | `AngularContactBallBearing.cs::Plot3DModel` | `SingleRowAngularContactInnerRace.cs`；`SingleRowAngularContactOuterRace.cs`；`BallRoller.cs`；`StraightPocketCage.cs` |

源码事实：`RoBAS.csproj` 使用 .NET Framework v4.5.2、Eyeshot v12，且项目引用 `../NetLib/` 下若干外部工程；本次压缩包无完整 NetLib 项目。**无法以当前压缩包直接证明原程序可编译运行**，迁移基线应从源码、独立公式计算和必要的专家审查建立，不可把未经运行的 RoBAS 当作自动化 golden oracle。

### 1.2 已识别的高风险点（必须关闭后再认定算法正确）

- **R-01：节圆公式不一致。** `DeepGrooveBallBearing.cs` 中某构造路径存在 `Dpw = 0.5 * (d + d)`；`DGBGeometry.cs` 则使用 `(outsideDia + insideDia)/2`。记录完整调用路径，确定哪个属于死代码/实际路径，不能直接照搬。
- **R-02：角度单位风险。** `ACBGeometry.cs` 中三角计算使用 `Math.Cos(alpha)` / `Math.Sin(alpha)`；部分调用处接触角以“度”标注。须追踪调用者并显式转换度→弧度；测试 α=0°、15°、25°、40° 等边界/常用输入（仅为几何测试用例，非设计推荐）。
- **R-03：内部米与外部毫米混用。** `BallRoller.cs`、`CylinderRoller.cs`、`StampingCage.cs` 等对象属性内部储存米、getter 输出毫米，且部分计算中有隐式换算。建立字段级单位追溯表，V2 内部**统一毫米**。
- **R-04：经验数值含义不明。** 例如滚动体数 `186`、沟曲率系数、经验壁厚/挡边因子、保持架板厚及 1.02 倍兜孔尺寸等，须标明来源和适用前提，不能解释为通用标准。
- **R-05：保持架几何复杂。** `StampingCage.cs` 包含多次切削、半保持架、铆钉孔等。先完成无保持架几何核心，再独立验证精简保持架，最后还原完整冲压保持架。不能用随意生成的圆环冒充完整保持架。
- **R-06：知识产权/授权。** RoBAS 是师兄软件，移植源代码或派生算法前应确认研究组授权、Eyeshot 及第三方工具约束；不把原依赖二进制提交到公开仓库。

### 1.3 旧 Bearing_CAD 的可用部分与限制

| 部件 | 可保留内容 | 不应当作 V2 通用架构的内容 |
|---|---|---|
| `cad02_pipeline.py` | B-Rep 导出、签名/缓存、检查的思路 | 固定 `housing/bushing/shaft` 三实体，固定输出列表 |
| `cad_workbench_drawing.py` | 真实截面、投影和 DXF/SVG 的经验 | 滑动轴承专属参数、画布坐标、固定剖面和标注 |
| `cad03_server.py` | 本地 API/文件服务原型 | 固定路径 `/api/cad02/*`，固定输出白名单，缺少通用任务模型 |
| `viewer.js` | Three.js 相机/灯光/轨道交互 | 固定三零件、固定显隐控件与爆炸向量 |
| `generate_cad.py` | 旧滑动轴承演示兼容 | 不作为滚动轴承几何原语库 |
| `.github/workflows/*` | CadQuery/OCP + 前端 CI 基线 | CI 结果不能代替真实滚动轴承工程验证 |

**注意：** 旧仓库 CI 固定 Python 3.11 + CadQuery 2.5.2。新环境以此作为起始兼容性基线；任何升级单独 PR、记录 OCCT 版本并重跑全套几何回归。开发时不要将当前机器安装的其他版本默认为等价。

---

## 2. 目标架构与职责边界

```text
多 Agent 设计/优化/审核系统
    │ Read-only DesignSnapshot (candidate/version/geometry/provenance)
    ▼
CAD Adapter 〔可信上下文隔离；快照映射；任务创建〕
    │ CadGenerateRequest
    ▼
CAD Application Layer 〔参数合法性、策略分派、任务状态、内容缓存〕
    │ ResolvedGeometrySpec
    ▼
Geometry Domain
    ├── Plain Journal Builder（后续适配）
    └── Rolling Bearing Builders
         ├── Deep Groove Ball
         ├── Cylindrical Roller N/NU/NJ/NUP/NF
         └── Angular Contact Ball
    │ List[Part(shape, role, name, location, metadata)]
    ▼
OCCT Geometry Verification 〔闭合性、尺寸、体积、干涉、拓扑、装配〕
    │ B-Rep Assembly
    ├── STEP Export (assembly + selected components)
    ├── Mesh Export (STL / optionally glTF)
    ├── HLR + Section + Drawing (SVG/DXF, later)
    └── Quality Report / Manifest / Provenance
    ▼
Artifacts Store + API + Three.js viewer
```

### 2.1 设计边界

- **设计计算、经验参数、标准参数**：来源于设计引擎/规则库，或经明确标记的 `legacy_robas` 派生策略；CAD Builder 不允许编造几何规则。
- **几何运算**：参数确定后纯函数/确定性执行，无 LLM 动态生成 OCCT 运算代码；失败返回机器可读错误与定位信息。
- **审批**：CAD 服务只读接收可信候选上下文；不接受任意请求自报 `CONFIRMED`、`confirmed_by`。发布权仍由多 Agent 主状态管理器持有。
- **展示**：Three.js 仅渲染网格、装配树、剖切和交互；不能用视觉效果替代 B-Rep 有效性检查。
- **工程图**：V2 初期输出结构复核图，待规范审图及图签、公差、制图约定完备后才允许进入正式发布流程。

### 2.2 代码目录设计

```text
Bearing_CAD/                         # 现有仓库，V2 在隔离分支开发
├── bearing_cad/                     # 新核心包；新模块不依赖旧版 app.js
│   ├── domain/
│   │   ├── enums.py
│   │   ├── specifications.py        # typed immutable specs
│   │   ├── provenance.py            # 参数来源 / 经验推导标记
│   │   ├── geometry_report.py
│   │   ├── parts.py                 # Part / AssemblyModel / Transform
│   │   └── errors.py
│   ├── rules/
│   │   ├── resolver.py              # explicit / verified-legacy strategies
│   │   ├── references.py            # 参考公式与版本
│   │   └── validators.py
│   ├── geometry/
│   │   ├── primitives.py            # ring, revolve, annular groove, boolean
│   │   ├── profiles.py              # 参数化轴截面
│   │   ├── placement.py             # rolling element array
│   │   ├── validators.py            # BRepCheck and assembly checks
│   │   ├── rolling/
│   │   │   ├── deep_groove.py
│   │   │   ├── cylindrical.py
│   │   │   ├── angular_contact.py
│   │   │   ├── cages.py
│   │   │   └── common.py
│   │   └── sliding/                   # 先保留接口，后续移植旧引擎
│   ├── application/
│   │   ├── registry.py
│   │   ├── generate.py
│   │   ├── artifacts.py
│   │   └── jobs.py
│   ├── export/
│   │   ├── step.py
│   │   ├── mesh.py
│   │   ├── drawing_svg.py
│   │   ├── drawing_dxf.py
│   │   └── manifest.py
│   ├── adapters/
│   │   └── design_snapshot.py
│   ├── api/
│   │   ├── schemas.py
│   │   └── routes.py
│   └── cli.py
├── frontend_v2/                    # 通用 Workbench：Phase 2
├── tests_v2/
│   ├── unit/
│   ├── integration/
│   ├── cad_kernel/
│   ├── interoperability/
│   └── fixtures/
├── docs/v2/
│   ├── source_traceability.md
│   ├── geometry_rules_register.md
│   ├── cad_contract.md
│   ├── cad_quality_policy.md
│   └── migration_decisions.md
├── environment-v2.yml
└── legacy/  # 仅在有明确理由且保持兼容时另行调整，初期不搬迁文件
```

**拆分原则**：`domain` 不依赖 CadQuery、OCP、Web、LLM；`geometry` 不依赖 Agent 状态；`export` 不依赖 `frontend`；`api` 不拥有任何机械计算规则。避免过度抽象：只先引入三种轴承共享、确实用到的 API。

---

## 3. 关键数据契约（建议 V1）

### 3.1 单位与几何坐标

- **外部/内部所有长度一律为毫米 `mm`，所有角度外部为度 `deg`，进入三角函数前显式 `radians(alpha_deg)`。**
- 轴承轴线采用全局 `Z`，中面 `Z=0`，外形宽度沿 `[-B/2, +B/2]`；`X/Y` 为径向平面；所有轴承遵循同一坐标规范。
- 几何数值必须有限，禁止 `bool` 冒充数字；在输入边界转换为规范化数值模型，不在几何类 getter 中暗藏米↔毫米转换。
- API 的参数精度策略显式声明（例如 0.001 mm 量化仅用于本项目首版输入和 hash）；OCCT 运算容差与工程公差分别处理，不互相替代。

### 3.2 请求结构（示例：数字是接口示例，不是工程设计推荐）

```json
{
  "schema_version": "cad.request/1.0",
  "bearing_family": "rolling",
  "bearing_type": "deep_groove_ball",
  "detail_level": "functional",
  "geometry_strategy": "explicit",
  "dimensions": {
    "bore_d_mm": 40.0,
    "outer_d_mm": 68.0,
    "width_mm": 15.0
  },
  "rolling_geometry": {
    "ball_d_mm": 9.0,
    "pitch_d_mm": 54.0,
    "element_count": 12,
    "inner_groove_radius_mm": 4.6,
    "outer_groove_radius_mm": 4.8
  },
  "cage": { "type": "omitted" },
  "requested_formats": ["step", "stl"]
}
```

说明：上面的数值并不保证互相可装配，它们仅用于表达字段结构。真实夹具必须由公式验证和专家复核后填充。`cage: omitted` 代表有意省略，输出中必须记录模型不完整，不可声称“完整轴承装配”。

建议定义两种互斥派生策略：

1. `explicit`：完整内部几何参数由设计结果给定且校验通过。用于精确设计模型。
2. `verified_legacy_rules`：在输入参数不充分时，用已逐条审核的 RoBAS 经验规则推导必要参数，同时记录公式标识、策略版本、输入值、派生值和 `ENGINEERING_REVIEW_REQUIRED` 状态。**未经审查的公式不得进入此策略。**

不建议用 `designation=6008` 就自行猜测制造商内沟曲率、滚珠数、保持架兜孔等内部细节。外形尺寸不能唯一确定内部结构。

### 3.3 `Part` 与 `AssemblyModel`

```python
@dataclass(frozen=True)
class Part:
    id: str                   # inner_ring / outer_ring / ball_001 / cage_001 ...
    role: str                 # 语义分类
    shape: object             # CadQuery/OCP shape only inside geometry layer
    material_hint: str | None
    location: object          # OCCT transform or local coordinate frame
    provenance: dict

@dataclass(frozen=True)
class AssemblyModel:
    bearing_type: str
    parts: tuple[Part, ...]
    resolved_geometry: dict
    engine_metadata: dict
```

规范：单列球轴承“无保持架”情况下的实体数应为 `2+Z`；一个实体保持架时为 `3+Z`。完整冲压保持架可能由多个半体/铆钉组成，数量须以 manifest 的语义树为准，不硬编码。装配不进行总布尔融合。

### 3.4 响应和产物清单

```json
{
  "job_id": "cad-job-001",
  "status": "SUCCEEDED",
  "engine_version": "v2.0.0-dev",
  "geometry_hash": "<server-generated-sha256>",
  "quality_level": "GEOMETRY_VALIDATED",
  "warnings": ["CAGE_OMITTED"],
  "files": [
    {"name": "bearing_assembly.step", "format": "step", "sha256": "<sha256>"},
    {"name": "assembly_preview.glb", "format": "glb", "sha256": "<sha256>"},
    {"name": "geometry_report.json", "format": "json", "sha256": "<sha256>"}
  ],
  "parts": [
    {"id": "outer_ring", "role": "outer_ring"},
    {"id": "inner_ring", "role": "inner_ring"},
    {"id": "ball_001", "role": "rolling_element"}
  ]
}
```

上面是目标格式示意。`quality_level` 是几何验收等级，不是主 Agent 的审批状态；审批信息只在主系统可信发布上下文中附加，不允许用户 POST 随意声明发布已确认。状态建议 `PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED`，具体采用是否必须异步由 PR-06 实测性能决定；避免为简单场景过早引入 Redis/Celery。

---

## 4. 几何算法的移植方法（技术路线）

### 4.1 迁移按“公式 → 几何配置 → B-Rep 零件 → 装配”分层

RoBAS 的 `Plot3DModel()` 同时承担实体、渲染与图层操作，V2 必须拆开：

- **Rules**：外形几何、球径/滚子直径、节圆、数量、沟道曲率、挡边、保持架参数。对每条公式附来源、单位、适用范围、审核人、测试夹具。
- **Profiles**：根据计算结果在轴向-径向平面定义封闭且不自交的内圈/外圈截面，经过旋转获得环状实体；复杂局部特征再以精确布尔运算获得。
- **Placement**：滚动体中心 `x_i=(Dpw/2)*cos(2πi/Z)`, `y_i=(Dpw/2)*sin(2πi/Z)`, `z_i` 由设计控制。球和滚子分别是球体或带定义长度/端部形状的回转实体。注意邻接滚动体间距应满足不重叠和必要的兜孔几何条件。
- **Assembly**：由 `Part` 表示语义对象，保留每一颗球/每一根滚子及可区分的内外圈和保持架，便于 STEP 装配及 Web 显隐。

### 4.2 深沟球轴承（首个几何里程碑）

1. 验证 `d>0`、`D>d`、`B>0`、`Dpw` 在环形空间内、球径与沟道半径形成允许截面。
2. 用独立截面参数函数构建内圈、外圈，检查有效壁厚和沟道不贯穿实体。
3. 每个球使用同一解析球体母形加平面内定位，校验第 `i` 颗球距离轴线为 `Dpw/2`、总数 `Z`、相邻球间无意外碰撞。
4. 先省略保持架但标记 `CAGE_OMITTED`；再移植简化保持架；最后独立 PR 迁移冲压保持架半体/铆钉细节。
5. 记录装配分件数量、体积、包围盒、BRepCheck、导出回读、一份三视/剖切对照样例。

### 4.3 圆柱滚子轴承

- 首先实现 N、NU 两类核心结构，明确是内圈双挡边还是外圈双挡边；使用源文件中 N/NU 等分支作为映射参考，并向专业人员确认各类挡边组合。
- 依次扩展 NJ、NUP、NF，别把所有挡边变化硬编码在单个庞大函数中；采用小型 `FlangeConfig` 数据结构映射。
- 滚子直径、长度、节圆和数量从已校核 `CRBGeometry` / `CRBOptimizer` 公式提取；滚子端面、兜孔间隙、保持架窗孔分别测试。
- 测试滚子轴向尺寸、端面与挡边非预期穿透以及所有滚子中心位置。

### 4.4 角接触球轴承

- 首先纠正输入 α 的角度/弧度路径，再实现依赖 α 的内外圈非对称沟道几何。
- 验证接触角改变时沟道中心轴向偏移方向、大小和左右结构的一致性。
- 预载、实际接触变形/赫兹接触分析不属于 CAD 几何首期范围；如果输入缺少内部几何，只可输出明确标记的概念结构。
- 复用球阵列与装配组件，采用专用的非对称内外圈剖面及保持架。

### 4.5 保持架单独工程化

将 `StampingCage.cs`、`CylinderPocketCage.cs`、`StraightPocketCage.cs` 分成 **几何计算** 和 **建模运算**：每条尺寸规则都可脱离 OCCT 单元测试。初版可先支持明确规范的简化保持架；复杂冲压/铆接结构必须能够在高精细模式下输出。`detail_level` 推荐三个级别：`envelope`（外形占位）、`functional`（内外圈真实滚道及滚动体，简化或省略保持架）、`detailed`（被验证的保持架结构）。不同等级在文件及界面中必须可见，不能将 `envelope` 等同于精确模型。

---

## 5. 三维、二维、展示和 CAD 内核取舍

### 5.1 CAD 内核

- **权威几何：** CadQuery + OpenCascade，优先 `Workplane` + `revolve` / `cut`；必要时直接使用 OCP 完成复杂投影、截面和错误诊断。
- **实体可用性：** 拓扑检查 `BRepCheck_Analyzer`、正体积、封闭性/实体数量、装配碰撞和径向/轴向尺寸一致性；核心参数写入报告。
- **交互网格：** STEP 是权威几何；STL 或 glTF/GLB 是显示/传输格式；显示精度不能当作制造公差。
- **装配语义：** 将独立零件和 transform 写入内部模型与 manifest；导出 STEP 后人工及自动验证零件结构，不能仅依赖 `importStep().solids()` 的数量来保证名称语义完全保存。

### 5.2 二维图纸策略

- PR-08 首期：同一 B-Rep 产生轴向真实剖切、端面真实投影、中心线、关键外形尺寸 d/D/B、球径/滚子尺寸（若图纸需要）、图框、参数/规则版本标记；导出可解析的 SVG/DXF。
- 二期：隐藏线样式、滚动体/保持架特殊剖视表达、尺寸样式、公差与表面粗糙度、技术要求、标题栏及图号。
- 不以对 STEP 的截图冒充 DXF；不以自由绘制的同心圆示意代替真实剖视；制图约定应结合适用的 ISO/GB 标准和专业老师审核。

### 5.3 Three.js Web 工作台

- 设计零件树动态加载（内圈、外圈、球/滚子组、保持架及子组件），支持每组单独显隐、透明、爆炸、剖切、模型重置、自动相机适配。
- 参数编辑仅用于 CAD 独立工作台或 `DRAFT` 候选预览，不能覆盖多 Agent 已确认值；明确展示“设计来源、完整性等级、是否通过校核”。
- 不再展示旧 `CAD-02 Day3` 等研发标签；UI 分区围绕“结构参数 / 三维装配 / 二维图纸 / 模型检查 / 下载与溯源”，由一致布局实现。

---

## 6. CI、测试矩阵与门禁

### 6.1 四层质量保证

1. **Pure unit tests**：单位、公式、边界、角度、滚动体坐标、`geometry_hash` 稳定性，不依赖 OCCT。
2. **Geometry/kernel tests**：每个零件有效、封闭、正体积、尺寸、局部壁厚、沟道轮廓、组件间不合理体积干涉；测试至少 3 种有效尺寸 + 每种 3 种非法/极端输入组合。
3. **Import/export tests**：实际 STEP 输出及回读，文件 hash、重复生成幂等、异常中断不留成功标识；DXF 文件 audit 和坐标单位检查。
4. **Visual & expert review**：FreeCAD 等独立软件打开、零件数量/部件定位/剖视外观截图、与 RoBAS 几何/设计公式对照；专业人员签字复核高风险规则和制造图要求。

### 6.2 机械几何测试不能只依赖 `isValid()`

- 外形尺寸：包围盒的 X/Y 应在指定 `D`，Z 应在 `B`（适用于完整圈体/装配外形）；局部零件须使用自己的尺寸约束。
- 同轴性：内外圈轴线同为全局 Z；球组节圆位置相等且相邻角差应为 `2π/Z`。
- 滚动体数量：`Z` 个不同零件 ID；相邻零件最小距离符合设计策略，不重叠。
- 干涉：对理论允许接触/微小几何容差、保持架兜孔和滚动体之间的接触分别定义策略；出现正体积交叠且超阈值需阻断或明确预警，不能“一律允许接触”或“一律零干涉”。
- 体积：球可验证 `Z * 4πr³/3`、圆柱滚子体积可验证 `Z * πr²L`（无倒角时），对经过切槽的圈体用稳定回归数据检查体积区间，不伪造简单体积公式。
- STEP：确认单位 mm，几何有效，独立零件结构可读取；明确区分**拓扑通过**、**结构符合参数**与**经工程设计认可**三种等级。

### 6.3 质量等级与阻断规则

| 等级 | 说明 | 可做什么 |
|---|---|---|
| `PREVIEW_ONLY` | 演示或外形占位、几何未完整确认 | 浏览器预览，不可称正式 CAD |
| `GEOMETRY_VALIDATED` | 参数、B-Rep、导出回读、关键几何测试通过 | 下载工程复核模型 |
| `ENGINEERING_REVIEWED` | 参数规则、结构和图纸经过专业复核，有审查证据 | 可用于研究方案正式评审，不等同于制造审批 |
| `RELEASED` | 仅主设计系统在审批流程合规完成后授予 | 发布流程控制；仍依赖适用技术规范 |

---

## 7. PR 路线图（每个 PR 必须可独立合并）

| PR | 标题 | 输入/主要改动 | 交付物 | 验收门禁 | 依赖 |
|---|---|---|---|---|---|
| **CAD-V2-00** | 技术冻结与源码追溯 | 记录旧仓库基线和 RoBAS 源码、核对授权和环境；建立源-目标-公式台账 | `docs/v2/source_traceability.md`、规则风险表、环境及旧测试基线 | 不改业务行为；高风险公式有风险编号和定位 | 无 |
| **CAD-V2-01** | CAD 契约和包骨架 | 独立包、typed 参数、单位、几何策略、异常、零件/装配模型、注册接口 | 可导入安装的 Python 包与纯单测 | 0 个 CAD 内核依赖泄漏到 domain；非法输入全部拒绝 | 00 |
| **CAD-V2-02** | OCCT 基础构件与模型质检 | 环体、旋转截面、阵列、布尔/容差；几何检查；简易 STEP 例程 | `geometry/`、几何报告 | 真实 kernel CI 通过；STEP 读回；无无声异常 | 01 |
| **CAD-V2-03** | RoBAS 深沟球内外圈+球组 | 已审核 DGB 参数公式、内外沟道实体、Z 个球、装配 | `rolling/deep_groove.py` 和参照夹具 | 3 个尺寸有效；节圆/球数/沟道/无非预期穿透；STEP 可打开 | 02 |
| **CAD-V2-04** | 深沟球保持架专项 | 简化结构与 RoBAS 冲压保持架分阶段实现；兜孔/铆钉 | `rolling/cages.py`、不同 detail level | 兜孔位置数量正确；非预期碰撞阻断；无保持架时标记不完整 | 03 |
| **CAD-V2-05** | 导出与内容寻址成果 | 分件及装配 STEP、预览网格、manifest、hash 和原子写入 | `export/`、`artifacts.py` | 重复请求一致；文件篡改拒绝；断电/失败不伪造成功 | 04（部分可与 03 并行设计） |
| **CAD-V2-06** | CAD API 与任务管理 | 新路由、状态/错误、参数校验、下载安全边界 | `api/` 与服务集成测试 | 端到端可生成/下载；并发/非法输入/跨路径访问测试 | 05 |
| **CAD-V2-07** | 三维工作台 V2 | 动态装配树、显隐、分解、剖切、参数来源、质量级别及下载 | `frontend_v2/` | 不再假设 3 个部件；浏览器检查支持多零件；自动化 UI 测试 | 06 |
| **CAD-V2-08** | 圆柱滚子 N/NU/NJ/NUP/NF | RoBAS CRB 公式、挡边矩阵、圆柱滚子与保持架 | `rolling/cylindrical.py` | 分型逐项几何、轴向挡边正确；至少 N/NU 先过关 | 02、05、06 |
| **CAD-V2-09** | 角接触球轴承 | α 单位修正、非对称沟道、保持架、球组 | `rolling/angular_contact.py` | 多接触角方向/偏置校验、三组参数、实际 STEP 回读 | 02、05、06 |
| **CAD-V2-10** | B-Rep 驱动二维图纸 | 投影/剖切/线型/标注/图框/DXF-SVG | `export/drawing*` 与验收样张 | 实体-图纸关键尺寸一致、DXF audit、第三方查看、复核图明确标记 | 07~09 |
| **CAD-V2-11** | 多 Agent 集成与正式验收 | Snapshot Adapter、候选隔离、确认/草稿、版本失效、端到端链路 | `adapters/`、系统集成测试与发布流程文档 | 用户未确认不发布；无权限伪造；设计修改触发失效；保留追溯 | 07~10 |

> 建议先将 CAD-V2-00~03 作为**第一轮交付**。只有 PR-03 几何证据足够，才投资保持架、服务 UI 和其它轴承类型。每个 PR 只完成标题所定义的边界，不提前实现下一阶段内容。

### 7.1 各 PR 具体任务及验收证据

#### CAD-V2-00：冻结和审查（绝对不要跳过）
- 创建 `feature/cad-v2-00-audit`，记录 main commit SHA、运行旧项目现有 CI/本地测试情况；不会运行的测试写出缺失依赖。
- 提取 RoBAS 三条 `Plot3DModel` → Geometry → Race/Roller/Cage → Eyeshot 的调用链和依赖图。
- 建立 `source_traceability.md`：每条几何公式：原文件/行、原变量、单位、目标字段、函数调用者、公式适用范围、可疑点、测试样例、审核状态。
- 授权核对：确认哪些源代码可在公开仓库使用，未确认前只记录路径和技术分析，不复制源码或二进制。
- 提交 `PR_REPORT.md`：文档链接、检查结果、风险及延期项目；禁止当作几何实现 PR。
- **DoD**：能从“深沟球球径/球数/节圆”一路追到实体生成；两处高风险公式进入问题台账；旧程序 main 不能被改动。

#### CAD-V2-01：契约
- `bearing_family`, `bearing_type`, `detail_level`, `geometry_strategy` 采用明确枚举；拒绝未知字段；带版本的 spec。
- 单位转换仅在 RoBAS 来源适配器发生，V2 domain 参数统一 mm；角度 `contact_angle_deg` 转 radians 的函数只有一个入口。
- 分离 `source_parameters` / `derived_parameters`，保留来源类别 `DESIGN_EXPLICIT` / `REVIEWED_LEGACY_RULE`。
- 定义 `Part`, `AssemblyModel`, `GeometryValidationReport`，builder 协议返回 Parts。
- **DoD**：纯 Python 单元测试覆盖 NaN、inf、负数、bool、非法枚举、缺少关键值、D<=d、Z<1、无效角度、单位 hash；无需导入 OCP 即可运行。

#### CAD-V2-02：几何内核
- 完成 `ring`, `revolve_profile`, `ball`, `cylinder_roller`, `circular_pattern`, `cut_groove` 的最小接口；测试 shape 的容差、闭合轮廓、有效性。
- 建立 **不依赖轴承类别** 的几何检查器；输出可机器解析 report。
- 实现最小真实 STEP roundtrip；锁定 Python/OCCT/CadQuery 版本。
- **DoD**：容器/Conda 环境可重建，完整 kernel 检查通过，具有失败时的详细诊断；不存在用于“修好”无效几何的静默 fallback。

#### CAD-V2-03：深沟球最小有效模型
- 实现 DGB 的内圈、外圈闭合截面和沟道实体；球组按参数 `Z`、`Dpw` 排列；不包含保持架时明确 `CAGE_OMITTED`。
- 制作不少于 3 套有效夹具；其中一套以 RoBAS 默认几何（`DGBGeometry` 的默认内孔 100 mm、外径 180 mm、宽度 30 mm）作为**待复核来源**，不把默认内部参数当作通用标准。
- 完成 3D 投影截图、STEP 第三方打开、边界用例与几何报告。
- **DoD**：每个球位置满足理论阵列位置，球组不自交，内外圈 B-Rep 有效；所有可疑 RoBAS 公式已有采用/修订/弃用结论。

#### CAD-V2-04：保持架
- 实现 `omitted / simplified / stamping_detailed` 版本，各有独立精度标签和导出说明。
- 迁移保持架几何规则到纯函数测试；以球中心轨迹和兜孔/铆钉位置验证。
- **DoD**：详细保持架和球无超约定穿透、布尔稳定、零件完整度可审计。若复杂冲压未验收，PR 只能交付简化等级，**不得谎称完成“详细保持架”**。

#### CAD-V2-05：导出
- STEP 作为权威成果；网格文件必须来自同一组 `Part.shape`；用 `CadQuery Assembly` 组织实体，测试不同出口保存零件名的行为。
- 工件 hash 应包含规范化解析后结构参数、builder/rules/engine 版本、detail_level、导出配置和影响几何的 OCCT 版本；候选 ID 等业务上下文在单独关联记录中使用，防止缓存误关联；不可变文件用内容 SHA256 校验。
- **DoD**：不覆盖他人的产物；错误中断没有成功标记；错文件不能静默复用；下载路径无 traversal 风险。

#### CAD-V2-06：API
- `POST /api/v2/cad/jobs` / `GET /api/v2/cad/jobs/{job_id}` / `GET /api/v2/cad/artifacts/{artifact_key}` / `GET /api/v2/cad/artifacts/{artifact_key}/files/{name}`；也可在 PR 方案中证明同步接口足够，先实现同步 facade，避免过早分布式化。
- 拒绝不可信的 `approval_state`、候选伪造身份；API 必须做服务端验证、大小限制、输入字段白名单和任务结果关联。
- **DoD**：真实 CAD 生成成功、错误状态可读、文件返回对应 SHA256、非法请求不会写出成果。

#### CAD-V2-07：工作台
- 在 V2 frontend 中用 manifest.parts 动态构造零件树；单件和零件组显隐、爆炸、半剖、透明、视角、自动缩放。
- 左侧参数/右侧三维/下方工程图或通过标签页设计，工程上突出参数来源、状态和模型完整性，去除老的研发 day 标识。
- **DoD**：Z=8 与 Z=20 等不同数目模型使用同一 UI，不需新增硬编码；与下载 STEP 生成源 hash 相同；浏览器测试通过。

#### CAD-V2-08：圆柱滚子
- 建立 `FlangeConfig` 映射 N/NU/NJ/NUP/NF，先 N/NU；详细结构由轴承方向人员审查，尤其 NUP 的活动挡边结构可能需要独立零件。
- 圆柱滚子建模按节圆分布；逐项校验挡边宽度/滚子长度/轴向间距与保持架兜孔。
- **DoD**：五种结构在相同共用外形下出现正确差异，各结构都有命名独立零件和 STEP 检验。

#### CAD-V2-09：角接触球
- 内外沟道截面非对称；所有三角计算只调用 radian-normalized math 函数；标明接触角方向和右/左组合设定。
- **DoD**：15°、25°、40° 结构相对偏移符合解析公式与人工复核；多个边界/非法角度拒绝；装配 STEP 回读。

#### CAD-V2-10：二维图纸
- HLR、实体剖切、轮廓截面、投影的稳定采样与 DXF/SVG 出口；图纸显示使用与 STEP 相同的 hash。
- 显示层与规范标注层分离；首版只提供标记为 `DRAFT REVIEW DRAWING` 的结构复核图。
- **DoD**：A3/A4 图框布局至少一个模板；DXF audit 无错误/自动修复；可在第三方 CAD 软件打开；专业审图问题单形成闭环后才提升图纸等级。

#### CAD-V2-11：与多 Agent 主系统集成
- 从可信状态仓库只读获取 `candidate_id/version` 及 geometrical snapshot；冻结提交时输入数据；引擎不拥有主系统用户确认字段。
- `DRAFT` 可预览/出复核成果；`RELEASED` 必须检查主系统对应版本审批状态、文件 hash、规则复核及图纸状态；candidate 更改后旧链接不误当最新。
- **DoD**：覆盖候选 A/B 隔离、未确认、驳回、版本更新、参数冲突、导出失败重试、用户身份伪造、缓存复用；已确认状态只能由主系统转变。

---

## 8. PR 工作方法（给 Codex 的作业规程）

1. **每次只给 Codex 一个 PR。** 起始信息包括：本规划文档、冻结 base SHA、该 PR 源码范围、允许修改文件、测试命令、明确的 DoD。
2. **先分析后动手。** Codex 必须报告依赖、预期修改点、既有风险；第一轮开发无需“全系统重构”。
3. **保持边界。** 不修改多 Agent 主项目状态确认权限；不更改旧 `main` 现有工作流；所有破坏性修改必须写迁移说明。
4. **所有失败可见。** 如果本地缺少 Eyeshot、原工程依赖、FreeCAD/OCCT，明确写出“无法验证”的项目，不得编造通过日志。
5. **PR 描述完整**：设计选择、来源映射、代码列表、测试结果、工件位置、图形截图、已知限制、是否需要专家复核。
6. **审查关卡**：PR 合并前机械意义的关键问题必须由轴承专业人员审查，自动化只能证明软件执行和某些几何关系。
7. **分支建议**：`feature/cad-v2-00-audit`、`feature/cad-v2-01-contract`……；主分支设保护，禁止 force push 和无人审查直接合并。
8. **证据应入库**：测试脚本、JSON 夹具、审核台账、必要的轻量截图和工件清单；不应将大体积 STEP/STL 二进制工件全部永久堆在 Git 历史，使用 CI artifacts 或独立存储。

### 单 PR 自检报告模板

```markdown
# CAD-V2-XX 验收报告
- 目标/非目标：
- 基线 main SHA / 分支 / 最终 commit：
- 源代码来源与已校核公式：
- 修改文件与新增契约：
- 测试命令与原始结果（成功/失败/跳过）：
- B-Rep 有效性/包围盒/干涉/STEP 回读报告：
- 第三方 CAD 人工验收证据（如适用）：
- 与旧系统回归结果：
- 限制、工程疑点、专家待确认：
- 是否满足 DoD：是/否；若否，阻断合并：
```

---

## 9. 首轮落地里程碑与决策门

### M0（完成 CAD-V2-00）
- 已知哪些 RoBAS 类是真正调用的建模路径、哪些公式不一致、每一项输入/输出单位。
- 新旧系统边界已冻结，审批/缓存/输出契约已草拟。
- **Go/No-Go**：若无法确定重要内部几何规则来源，先让老师/师兄复核，不进入 PR-03 “工程有效”认定。

### M1（完成 CAD-V2-01~02）
- 内核不依赖 UI，可通过 CLI 传 JSON，生成几何/单件 STEP；产出基本质量报告。
- 纯函数层和 OCCT 内核层分别有稳定测试。
- **Go/No-Go**：验证环境不稳定、STEP 回读失败、参数单位未统一时，暂停扩展轴承类型。

### M2（完成 CAD-V2-03）——最重要技术检验点
- 一个深沟球轴承能稳定生成结构合理的内外圈、沟道和滚动体阵列；STEP 可打开；多尺寸验证通过。
- 概念版与经过审核的真实内部几何分开标记。
- **Go/No-Go**：如误差或拓扑问题无法解决，先强化原语/几何规则，不投资源于网页美化。

### M3（完成 CAD-V2-04~07）
- 可配置保持架、可回读产物、可用 Web 三维工作台、通用模型清单和下载服务。
- 不再假设三件零件，CAD 可由 HTTP 调用。

### M4（完成 CAD-V2-08~10）
- 三种轴承同一个内核/接口；二维复核图和 STEP 一致；手工 CAD 检查与专家审图可追溯。

### M5（完成 CAD-V2-11）
- 主系统正式调用 V2 CAD，基于候选快照自动生成、验证、预览和下载；用户确认权限不被 CAD 修改。

---

## 10. 当前明确不做的事情

- 不将 RoBAS WinForms/Eyeshot 整体复原；不引入缺失的商业依赖作为生产服务。
- 不强制先改写主多 Agent LangGraph/StateManager；只在 PR-11 通过可信 Adapter 对接。
- 不同时使用两套权威 B-Rep 引擎（例如浏览器 occ.js 与 Python OCCT 两套分别独立出设计真值）。
- 不在 PR-03 追求真实铆接保持架、密封圈/防尘盖/润滑油等所有复杂细节。
- 不默认通过某种 UI 演示就称为“正式制造工程图”；在审图规则和参数可信性不足时只给结构复核产物。
- 不由 LLM 在运行时生成任意 CAD Python 脚本后执行；Agent 提供符合 schema 的数据，不提供任意可执行 CAD 代码。

## 11. 不确定性与待复核工作（不阻止 PR-00~02 开始）

- RoBAS 源码能否授权公开再利用；需要师兄/课题组确认。
- 两条高风险几何公式的正确版本以及经验系数的工程适用边界。
- 多 Agent 主项目实际 state contract：需要在 PR-11 前以当前主项目代码对齐 `candidate_id/version/approval` 的真实字段。
- 最终采用何种标准定义“可制造二维图纸”以及审图/签署责任，需轴承老师确定。
- 是否需要运行时部署到 Linux 服务端；当前研发可优先 Windows 本地 + GitHub Actions Linux 内核验证，避免平台偶然差异。

---

## 12. 立即执行的第一件事

**先执行 CAD-V2-00：冻结基线与源码可追溯审查。** 它只产生证据与文档，不会破坏旧代码，是目前风险最低、收益最高的起点。不要直接让 Codex 开发深沟球轴承并边写边猜 RoBAS 公式。

配套 Codex 提示词另见 `CAD_V2_Codex_PR00_执行任务书.md`。
