# PR-2D-04 — 圆柱滚子轴承原版尺寸、公差与挡边来源核对

## 原版源码和适用范围

由用户上传的 `RoBAS(1).zip` 提取：

- `Controls/CylinderRollerBearing/CylinderRollerBearingServer.cs:SetCADTextValue`（569–932 行）共有 **46 个直接赋值分支**。
- `Core/RollerBearing/CylinderRollerBreaing/CylinderRollerBearing.cs:69–87`：轴承宽度、内外径 public getter 保留 0.01 mm。
- `BearingModel/Roller/CylinderRoller.cs:46–65`：滚子长度 0.01 mm，滚子直径 getter 不额外舍入。
- `Core/RollerBearing/CylinderRollerBreaing/CRBOptimizer.cs:97–115`：优化器滚子直径 public getter 保留 0.0001 mm。原版 `a2/E1/E2` 使用优化器 getter，而 `E` 和数据库滚道宽度公差使用滚子实体的 **0.01 mm 长度 getter**。
- `Core/RollerBearing/RollerGeometry.cs:128–133`：内圈沟道位置 public getter 保留 0.01 mm。
- `CRBGeometry.cs:53–95`：**先由未舍入的节圆和滚子直径** 求原始沟道与挡边，然后经 getter 输出 0.01 mm。
- `Utility/DataBase/DataControl.cs:1530–1563`：`GetRollerGrooveWidthDeviation` 先以源 getter `RollerLength` 搜索 `CRBData.db / 滚道宽度公差`，首条满足 `rollerLength >= ...` 的行提供 `E_Upper/E_Lower`（原版无 `ORDER BY`，本次不擅改）。
- `CRBOptimizer.cs:417–469`：根据孔径与外径区间选择 Kd2/KD2；原版源码不对超出区间的数据建立合法系数。

## 本轮实际迁移

恢复以上 **getter 的先后舍入顺序**，避免如实际滚子长 10.004 mm 时，原版 getter 10.00 mm 应落入第一公差档（+0.07/-0.03），却被未舍入的 10.004 查询为第二档（+0.09/-0.03）。

`E1/E2` 只在调用方明确提供已核对的 `inner_groove_position_mm` 时生成：先按原版位置 getter 保留 0.01 mm，再以 C# `(int)` 向零截断计算 0.5 mm 台阶。**不猜测**当前 OCCT 内圈实际沟道位置等于原版默认值。

`d2/Dd2`：原版在原始（尚未两位舍入）的节圆、沟道尺寸上施加 Kd2 系数，最后才执行挡边 getter 两位小数舍入。本次恢复这条来源路径，并仅在原始参考挡边尺寸与当前实际三维 integral rib-tip 值在严格精度内一致时填充标注。即使两者显示值同为 49.4 mm，也不能把实际 49.4000 与原版 49.4037 mm 误判成相同实体。

证据新增 `legacy_design_evidence.original_source_rib_tip_mm` 和 `original_source_rib_matches_cad`，区分实际匹配、无该挡边和原版系数越界。

## 原版 46 个直接赋值分支覆盖路线

| 类别 | 分支数 | 当前处理 | 限制 |
|---|---:|---|---|
| 型号、d/D/B、Dw/Lw/Z | 7 | `drawing_variables` | 需与真实轴承型号匹配 |
| Cr、Cor | 2 | `drawing_legacy_ratings` | 原版 CSV 系数缺失不能当合法零额定载荷 |
| 两类倒角（含 r2/r3/r5/r8）的偏差 | 24 | `drawing_legacy_chamfer` | 必须命中原版 SQLite 倒角表 |
| De、di、a、a2、挡边/上下偏差、E/E1/E2 | 13 | `drawing_legacy_crb_source`、`drawing_legacy_roller`、`drawing_legacy_dimensions` | 只有实际几何匹配或有已审核显式来源才自动填写 |
| **合计** | **46** | | 不包含循环里按列名读取的标准表 |

原版还从游隙、粗糙度、宽度偏差、两套技术条件表以及滚道宽度公差 SQLite 表读取 TEXT。这些查表项不属于直接赋值分支，本轮不冒充已完成所有数据库变量审核。

**特别注意：**原版 CRB `SetCADTextValue` 没有直接给保持架尺寸进行赋值。原版 `CylinderPocketCage` 有独立三维属性和孔径/窗宽公式，但不等于它们在原版 DWG 中经过验证。本轮不把无来源的保持架文字补进工程图。

## 出图缓存和实机核对

给 CRB 增加仅作用于圆柱滚子轴承的 `crb_drawing_getter_parity` 缓存版本标识，使新计算来源诊断不会被历史 manifest 缓存遮蔽。其他两种轴承的成果键不变，无需清除 `artifacts`。

核对用例（含原版 SQLite 第一、第二公差档；`a/a2/E/E1/E2`；内外挡边实际匹配/不匹配；N/NU 的缺失挡边；缓存隔离）已写入单元测试。

## 待用户 Windows 验收

1. 在隔离工作目录中运行 `python -m pytest tests_v2/test_drawing_legacy_roller.py tests_v2/test_drawing_legacy_crb_source.py tests_v2/test_drawing_runner.py -q`。
2. 使用授权 Windows CADImport 和原版 RoBAS 资源，生成 N 构型四张 DXF，重点检查 `E`、`E_Upper/E_Lower`、`E1/E2`、`a/a2`、`De/di`、`d2/Dd2` 和公差。
3. 仅在逐一核对实际挡边、独立挡圈和原始模板组合后再尝试 NU/NJ/NF/NUP；这些模板组合仍需 AutoCAD 核验，不是自动证明源装配等价。
4. 检查新 `drawing_manifest.json` 中的来源证据与图纸实际 TEXT；`manufacturing_approved=false` 不变。

## 未完成项

- 三类轴承全数据库标准公差与技术条件、质量、额定载荷、型号核验列在后续阶段。
- 本 PR 不修改原版 RoBAS 程序、不创建新 DWG、不引入制造标准假值、不修改 OCCT B-Rep 或网页 UI。
