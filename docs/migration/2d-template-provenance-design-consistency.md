# PR-2D-08：真实 DWG 命中项追溯与设计一致性

## 证实的原版数据源

原始提供的 `RoBAS_Resources.zip` 内有 **`Data/BearingType.db`**
（不是 DGBData.db，也不是我们自行编造的 ISO 规则）。其中
`深沟球轴承型号目录` 的精确匹配行包含：

| 型号 | d (mm) | Dd (mm) | B (mm) |
|---|---:|---:|---:|
| 6008 | 40 | 68 | 15 |
| 6208 | 40 | 80 | 18 |
| 6308 | 40 | 90 | 23 |

只按 exact `model = ?` 查询此原版 SQLite，保留文件摘要。
已有 source row 的 DGB 标签如果与显式设计 d/D/B 不同，拒绝生成
错误型号图纸，例如禁止 **40×68×15 mm → 6208/P5**。
`diameter_series` 的检查仅对 RoBAS 型号前缀中能验证的系列使用，
依据 `DGBOptimizer.SetCoeffccient(...)` 的 `Substring(0,2)` 源码
路径。检查大小为公称尺寸，绝不引入制造公差推断或更改 B-Rep。

**不在目录中的型号**包括非标型号，不强行标为错误；报告
`MODEL_DIMENSIONS_NOT_VERIFIABLE_REQUIRES_REVIEW`。DGB catalog 不存在
时也保持未核实状态，不假设型号与尺寸匹配。ACB 和 CRB 当前没有
可以完整等价查表的型号目录，保留未确认的来源告警。CRB 的
N/NU/NJ/NF/NUP 在用户型号前缀可识别时，必须与实际模板构型匹配，
否则阻断；不能识别的自定义型号不猜测，也不自动更改构型。

**关键点**：对的是最终送 CADImport 的模型变量文本。通过
`checked_values['model']` 输入的型号和直接 `model` 选项一视同仁。
核查不宣称已独立测量 OCCT 3D 实体；仅核对与 3D 请求共用的、受
契约确认的参数和原版目录。若无 d/D/B 的标准目录证据，结论明确
不等于“型号有效”。

## 真正命中的模板字段追溯

沿用 **CADImport Bridge `matched_keys`**，不以全数据库缺口数量衡量
工程图完整度。每张图纸 `sheets[*].variable_diagnostics` 新增
`matched_variable_provenance`：

- `name`，实际命中的 `matched_text_entities` 数；
- `row_indices`（原 SQLite 变量表逐行索引），`source_tags`；
- `requested_value`（送给 CADImport 的值，**不是从 DXF 重新识别出的文字**）；
- `state = TEMPLATE_USED_MISSING / POPULATED_UNREVIEWED`；
- `confirmed_design_field`（仅对真正来自确认设计参数的 `d/Dd/B_/Dw/Z/Lw/alfa1` 标注）；
- `review_flags` 记录同名重复变量行存在不同源值，不悄悄选一个。

原有的 `unfilled_template_variable_names` 和
`unfilled_database_unused_names` 不变；新增
`source_conflict_template_variable_names` 汇总仅图纸命中的重复来源
歧义。未在当次 DWG 中命中的空值仍作为 **DATABASE_UNUSED**，
不当作图纸缺陷。对 W09/W16 等未有可信来源的标注继续保留空值，
并明确属于尚需审查的模板命中缺口。

每张 `sheets[*]` 同时写入实际 `template_file` 名称及现有
`template_sha256`，特别是 NUP 的第五张 `loose_rib.dxf`
（原版 `NUP-12.dwg`）。NU/NJ/NF/NUP 的
`INFERRED_SOURCE_FILES_AUTOCAD_REVIEW_REQUIRED` 原标志保持不变。

## 自动原版候选值与人工输入优先级

继续维持已有实现的“先自动填充→后 restore_checked_values”顺序，
避免覆盖经验证的 `checked_values`。额外记录
`legacy_input_override_evidence` 中自动来源键与用户提供
`legacy_values` 的交集和明显不一致项。传入
`legacy_values` **不能自动代表工程审核**，也不赋予来源认证。

新 Manifest 来源审查版本和实际目录 SHA 进入 drawing bundle 的
不可变缓存身份；目录被替换、手动型号更改、审核字段不同都不会
继续读取旧的模型检查结果。

## Windows 实机审查

从最新 PR 分支，在合法 Windows + CADImport 环境生成：

1. DGB `6008/P5` 且 40/68/15，核对型号及四张图纸成功；
2. 同样几何强制 `6208/P5`，应在导出前收到型号尺寸冲突错误；
3. DGB 未知/自定义型号，Manifest 应记录尚未目录核实，而非伪造“标准匹配”；
4. CRB N/NU/NJ/NF/NUP：NUP 必须有活动挡圈第五张且源文件正确；
5. 选定每张图纸 `matched_variable_provenance` 与 DXF 实际 TEXT 逐项核查；
6. 记录所有 `TEMPLATE_USED_MISSING` 和来源歧义，区分真空缺与未使用 DB 变量。

本 PR 不修改原版 DWG、SQLite、CSV、CADImport、三维 OCC/STEP/STL。
自动 CI 通过 ≠ Windows 实际 CADImport/AutoCAD 通过 ≠ 制造批准。


## 补充：真实 DXF 中的未映射占位符

上面基于 SQLite `matched_keys` 的统计只能看到原版变量表实际命中的
TEXT；不能看到 **DWG 本身存在、但不在变量表中的文字**。对本次
开发前用户提供的 DXF 样例进行只读核查，发现：

| 历史 DXF | 残留文本 | 次数 | 性质 |
|---|---|---:|---|
| `assembly.dxf` | `Dw_Inch` | 1 | 无精确匹配的旧模板文字，需人工确认适用性 |
| `outer_ring.dxf` | `@DdS` | 2 | 与源变量名 `@Dds` 仅大小写不同，CADImport 精确匹配不会替换 |
| `outer_ring.dxf` | `Company` | 1 | 疑似原版图签保留文本 |
| `outer_ring.dxf` | `***` | 2 | 疑似模板占位文本 |

这是**历史用户样例**的结果，不宣称新 PR 已通过 Windows
实际出图。新功能只扫描导出的 DXF 模型空间 TEXT/MTEXT，将
`@...` 未列入数据库的精确 token、大小写不一致项以及有限的
已知原版字面量记录至每张图纸的
`suspected_unmapped_text_diagnostics`，并在 Manifest 汇总
`suspected_unmapped_template_texts`。它们是**待核查提示而非自动
替换规则**；不能无源依据改 `@DdS`、填 `Dw_Inch`、删除
`Company` 或 `***`。

前端仅增加现有状态栏和当前图纸诊断行的简要警告，避免在完整
Manifest 之外静默向用户交付未核实的标签。默认演示设计为原本
40/68/15 mm 深沟球，故前端初始型号由错误的
`6208` 调整为有源证据的 `6008`，初始直径系列由 2 调整为 0。
用户切换轴承类型或设计参数后仍须自行明确相应型号；不自动推断。
