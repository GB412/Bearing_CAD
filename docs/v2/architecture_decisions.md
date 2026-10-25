# CAD-V2 统一参数化轴承 CAD 引擎架构决策

状态：CAD-V2-00 设计基线，等待 CAD-V2-01 按本文件建立骨架；未实现代码。目标为从结构化设计参数生成可验证的滚动轴承 3D 装配、STEP/STL、同源二维视图和 Three.js 预览，并为多 Agent 系统提供稳定 adapter。此设计不宣称制造级或 GB/ISO 认证。

## 1. 决策摘要

1. 新建独立 Python 包 `bearing_cad/`；旧 `BearingCAD_Demo` 仅提供可选算法/测试方法参考，不作为 import/runtime 基础。
2. Python + CadQuery + OCCT/OCP 负责所有参数化实体几何；Three.js 只消费经验证 B-Rep 导出的 mesh/manifest，不自行生成替代实体。
3. 核心契约统一 mm 与 `*_deg`；内部角度只在数学函数边界转 rad；坐标轴线固定 Z、轴承宽度中心面 `Z=0`、节圆位于 XY。
4. 参数输入和派生设计分开：用户明确给出的尺寸/选择保存在 request，设计规则计算产生 DerivedGeometry/RuleTrace；不静默覆盖用户输入。MVP 所需 Dw、Z、PCD 等是显式输入还是推导输出，按轴承型 schema/decision table 明确标记。
5. 每个实体组件有稳定 ID 和独立 shape；球/滚子 instances 可表达共享几何 + 变换而不丢失独立语义。Assembly 不把所有滚动体 fuse 成单体。
6. 请求/API 适配、任务排队和 UI 不依赖 CAD builder；单纯函数 `build(request)->AssemblyModel` 可在无 HTTP 环境中运行。
7. CAD 产物状态只允许 `DRAFT` / `VALIDATED_GEOMETRY` 等引擎定义状态，不包含用户确认凭证，不意味着承载寿命、公差、材料或制造批准。

## 2. 建议包结构

```text
bearing_cad/
  __init__.py
  contracts/
    request.py                 # 版本化请求、类型选择 union、单位字段
    design.py                  # 规范化参数、派生量、rule trace
    assembly.py                # Component/Instance/Assembly DTO
    artifacts.py               # manifest、任务状态、错误 DTO
  schemas/
    rolling_common.py          # 单位/公共约束
    deep_groove.py
    angular_contact.py
    cylindrical_roller.py
  rules/
    validation.py              # 不依赖 OCCT 的结构/数值/可行范围检查
    formulas.py                # 有来源、有版本、有单测的已审几何关系
    registry.py                # bearing_type + schema/rule version
  geometry/
    primitives.py              # 有单位注释的基本 B-Rep 生成
    races.py                   # 内圈、外圈、沟槽、挡边构造
    rolling_elements.py        # 球/滚子及实例阵列
    cages.py                   # 有明确 cage kind 的笼与窗口/兜孔
    transforms.py
    checks.py                  # 拓扑、体积、包围盒、最小壁厚、配对关系
  builders/
    base.py                    # type -> validated geometry builder protocol
    deep_groove.py
    angular_contact.py
    cylindrical_roller.py
  drawing/
    views.py                   # HLR、剖面与投影视图
    dimensions.py              # 与几何值绑定的尺寸实体
    sheets.py                  # 图框、比例、标题栏与状态文字
    exporters.py               # DXF/SVG；图纸状态与格式版本
  export/
    step.py
    stl.py
    roundtrip.py
  preview/
    manifest.py                # 动态 part/instance/transform/material 清单
    mesh.py                    # 预览网格派生及质量配置
  jobs/
    service.py                 # 任务状态机/取消/重试边界
    cache.py                   # 内容寻址与原子发布
  adapters/
    local_api.py               # loopback HTTP adapter（可选）
    multi_agent.py             # 主系统输入输出 DTO adapter，不含建模逻辑
```

测试、fixtures、docs 不放进运行包：`tests/unit`, `tests/geometry`, `tests/export`, `tests/api`, `tests/browser`, `fixtures/rolling`, `docs/v2`。

## 3. 参数 Schema 与模型

### Request 基础 envelope

```json
{
  "schema_version": "bearing-cad.request.v1",
  "request_id": "caller-generated-id",
  "bearing_type": "rolling.deep_groove_ball",
  "unit": "mm",
  "parameters": {},
  "drawing_profile": {"sheet": "A3", "projection": "first_angle"},
  "export_profile": {"step": true, "stl": true, "mesh_tolerance_mm": 0.05},
  "requested_by": {"system": "multi-agent-design", "design_id": "..."}
}
```

轴承参数是按 `bearing_type` discriminator 的封闭对象，不接受任意字段。首期共同尺寸候选：`bore_d_mm`, `outside_d_mm`, `width_mm`；球轴承候选 `ball_d_mm`, `pitch_d_mm`, `ball_count`, `contact_angle_deg`, `inner_groove_factor`, `outer_groove_factor`, `cage_kind`; 圆柱滚子候选 `roller_d_mm`, `roller_length_mm`, `pitch_d_mm`, `roller_count`, `configuration` (N/NU/NJ/NF/NUP)。设计规则给出的值须记录在 `derived_parameters`，包括来源/公式 ID、rule version、单位和显式/推导来源。暂不把 catalog/optimizer 作为 v1 schema 默认值隐藏执行。

约束：finite 数值、明确的正值/角度范围、数量为正整数、内外径与宽度关系、与构型匹配的字段；输入错误返回 JSON Pointer 风格字段路径和稳定 error code。合法范围属于待评审规则，不能复用旧 demo 限值或直接声称行业标准。

### 领域实体

- `ComponentDefinition`: component_id/category/role/name/material_hint/shape(B-Rep)/source_rule_ids。
- `ComponentInstance`: instance_id/definition_id/transform/ordinal/parameters；滚动体单件 ID 稳定可定位。
- `AssemblyModel`: request hash、bearing type、normalized design、derived values/rule trace、components/instances、geometry checks、generation version。
- `ArtifactManifest`: schema version、request hash、generator/rules/CadQuery/OCCT versions、unit/coordinate convention、parts/instances、file path/hash/size/format、validation summary、draft status。

## 4. 分层职责与模块依赖

```text
Multi-Agent DTO ─┐
                 ├─> adapters -> Request Schema -> Rules/Validation
Local API/CLI ───┘                                    │
                                                     v
                         Builder Registry -> Bearing Builder
                                             │       │
                                      race/element/cage geometry
                                             │
                                             v
                                       AssemblyModel
                                        /    |     \
                                  checks  drawings  exporters
                                             |          |
                                             └──> manifest + preview data
                                                       |
                                                Three.js viewer
```

单向依赖：contracts 不导入 OCCT；rules 可依赖 contracts，不依赖 UI/HTTP；geometry 依赖 CadQuery/OCP 和已审规则；builder 组合 geometry；checks/export/drawing 消费 AssemblyModel/B-Rep；jobs/cache/service 调用 builder 并发布成果；adapters 转换输入输出但不推导几何。禁止从 viewer/API 回写 shape，也禁止 drawing 模块自己生成不同于 builder 的实体。

## 5. 数据流与错误状态

1. Adapter 接收 envelope，检查 schema 版本、请求大小、唯一 request id 和安全字段白名单。
2. Schema parser 规范化字段及数值表示，拒绝 NaN/Infinity/单位缺失/不支持轴承类型；产出 canonical request。
3. Rules 层执行范围、解析关系和来源检查；派生值带 rule id；需要用户决策的输入不静默推断。
4. Builder 生成独立 component definition/instances；所有 B-Rep 单位 mm、位置变换显式。
5. Geometry validator 检查每个 shape 非空、拓扑有效、solid 数、正体积、包围盒目标尺寸；装配关系检查预期相切/间隙/意外穿透并保存测量结果。硬错误不发布 artifacts；警告留在报告中但不能隐藏。
6. Export 阶段先写唯一 staging 目录，STEP 包含命名组件/实例，STL 单件及 assembly 可选；DXF/SVG 从同一 B-Rep HLR/截面和同一尺寸 DTO 生成。
7. roundtrip 阶段回读 STEP，并核对零件/实例数、总体包围盒、体积容差；完成 hash 后写 manifest，最后原子 rename 成 cache artifact。
8. Viewer 由 manifest 动态创建 meshes/零件树，使用 instance transform/material/category；请求切换时通过 job/request id 取消或忽略旧响应并清理旧 meshes。

稳定错误形态建议：`error_code`, `message`, `field_path`, `stage`, `diagnostic_id`, `retryable`, `details`. 例：`SCHEMA_UNSUPPORTED`, `PARAMETER_INVALID`, `RULE_UNRESOLVED`, `GEOMETRY_EMPTY`, `BREP_INVALID`, `ASSEMBLY_INTERFERENCE`, `EXPORT_STEP_FAILED`, `ROUNDTRIP_MISMATCH`, `ARTIFACT_HASH_MISMATCH`, `CANCELLED`, `NOT_SUPPORTED`. 禁止只回通用 500 丢掉诊断；外部响应可脱敏，服务日志按 diagnostic id 保留原因。

任务状态建议：`queued -> validating -> building -> checking -> exporting -> roundtripping -> succeeded`; 任何阶段可 `failed/cancelled`; cache hit 是已校验既有成果并标注 `reused=true`。失败成果保留诊断但不进入正式缓存 key；并发相同 key 应 single-flight，不能半成品抢占正式目录。

## 6. 缓存与制品身份

`request_hash = SHA256(canonical(schema_version, bearing_type, explicit params, selected rule/profile versions))`；`artifact_key` 另外加入 generator version、CadQuery/OCCT build、export profile 与 tessellation settings。包含几何的 transform、组件实例参数和视图模型配置影响对应的 hash。每个文件 SHA256；manifest 自己也可作索引/完整性记录，但不能出现对自身循环 hash。缓存只复用完整 manifest 校验通过的成果。用户确认/审批不混入 CAD 缓存状态，另由主系统保存授权/决策记录。

## 7. 图纸与预览边界

- Drawing 输入 `AssemblyModel + drawing profile + dimension DTO`; HLR 用于可见/隐藏边，OCCT section B-Rep 用于剖面边界/剖面线；尺寸文字数值必须引用校验后的模型参数，不再另算一套值。
- SVG/DXF 图纸需有 `DRAFT / NOT FOR MANUFACTURE` 明确状态，版本/单位/投影法/比例；尺寸、图层和格式都可机器审计。真正符合 GB/ISO 制图、GD&T、配合公差和制造审核需另立能力阶段。
- Preview manifest 的 mesh file 对应 B-Rep component/instance，含坐标 mm、变换矩阵、part id/category、颜色默认值、可见性组、爆炸方向建议和 hash。STL/mesh 只用于渲染，不得回输入 STEP 或执行几何校验。

## 8. CAD-V2-01 建议实现边界

PR-01 建议命名为“引擎基础契约与质量门禁”，只实现：

1. Python 包/构建元数据、锁定 CadQuery/OCP 环境和 CI 安装验证；需要固定 Windows/CI 可复现的 CadQuery+OCCT 组合。
2. v1 Request / DerivedParameter / Component / Assembly / ValidationReport / Manifest / Error 契约和 schema 测试；discriminator 至少声明三种目标类型，但未实现 builder 的类型必须返回 `NOT_SUPPORTED`。
3. Canonicalization/hash、版本/单位/坐标合同；简单非轴承的 OCCT probe 测试确认内核可用、STEP round-trip 可执行；不得把 probe 当轴承模型功能。
4. Builder registry 插件边界、错误 DTO、缓存 staging/原子发布的空骨架或独立 service 单测。
5. 从旧代码只抽取/重写核心验证方式，不迁移旧业务类，不引入 `.reference/RoBAS` 运行时依赖，不创建滚动轴承 B-Rep，不做 UI/API 接入。

门禁：环境缺少 CAD 内核时 CI fail fast；contract/unit/probe/STEP 回读通过；无既有滑动功能删除/修改；pytest 报告不允许真实 CAD 测试被 skip。进入第一个真实模型 PR 前另做公式审计决策与几何 fixture 审批。

## 9. 未决决策

1. RoBAS 源码及其学长作品的使用/改作/对外发布授权；Eyeshot 代码和库不可默认带入。
2. CAD-V2-01 的精确仓库根目录、Python 版本、CadQuery/OCP pin 和 Windows/CI 矩阵。
3. 用户/Agent 参数中哪些是设计目标、目录选择、可计算派生量；尺寸数据库和适用标准来源。
4. 深沟球 Z、滚道游隙/接触关系，角接触 alpha 定义/单位，CRB 构型挡圈语义及保持架来源。
5. 2D 交付等级、投影法、图幅/语言、标注规则及是否要求制造图。
6. 多 Agent adapter 的实际主系统 endpoint、同步/异步 SLA、artifact 生命周期和候选确认服务边界。
