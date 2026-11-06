# PR-2D-07｜原版额定载荷、重量、保持架与零件标注闭环

## 已核查的真实源码调用链

| 图纸类型 | gamma 输入 | 系数 CSV | Cr 公式 | Cor 公式 |
|---|---|---|---|---|
| DGB | `BallRoller.BallDiameter` (0.001 mm) / `BallRoller.PitchDiameter` (0.01 mm) | `球轴承零件相关系数.csv` | `DGBOptimizer.CalcuDynamicLoad` | `DGBOptimizer.CalcuRadialStaticLoad` |
| ACB | 同 DGB | 同 DGB | `ACBOptimizer.CalcuDynamicLoad` | `ACBOptimizer.CalcuRadialStaticLoad` |
| CRB | `CylinderRoller.RollerDiameter` (不舍入) / `CylinderRoller.PitchDiameter` (0.01 mm) | **`球轴承零件相关系数.csv`** | `CRBOptimizer.CalcuRadialDynamicLoad` | `CRBOptimizer.CalcuRadialStaticLoad` (不使用系数) |

来源：`Controls/{DeepGrooveBallServer,AngularContactBallServer,CylinderRollerBearing}/*Server.cs::SetCADTextValue`。**注意源码差异：**CRB 优化器内部的单输出 `SearchCoeffcient(gamma, out fc)` 查询滚子系数 CSV，但 CRB 出图服务使用 *双输出* `SearchCoeffcient(gamma, out fc, out fo)`，该签名来自 `BaseOptimizer`，故查询球轴承 CSV。本文选择忠实复制“二维出图”的调用链；这不代表原版 CRB 的这项选择是工程正确的，制造用途须由专家决定是否修复上游逻辑。

原版 `BaseOptimizer.SearchCoeffcient` 对 `Double.Parse` 的系数表第一列使用 `double.Equals` 精确匹配，不允许容差近似匹配。gamma 使用原版 `Math.Round(value, 2)` 的二进制浮点 scale-then-ties-to-even 过程。

## 载荷缺失和可信度处理

- 完整源 CSV 不存在、格式错误或非有限系数：抛出明确错误，不用虚构系数替代。
- gamma 未命中时，**原 C# 的 fc/fo 默认为零**；`calculate_robas_loads` 仍保留零数值用于源码数值对照，但 `apply_robas_loads` 不填入无效 `Cr` / 球轴承 `Cor`，而是在 `legacy_load_evidence` 中报告未匹配。CRB 的 `Cor` 不依赖系数，允许按原版公式填写。
- 表中确实存在零/负系数时，不将其作为有效 `Cr` 标注。值是否可用于制造仍需专业审核。
- `Cr` 和 `Cor` 输出单位 kN、保留两位小数；绝不声称工程验证通过。
- 只覆盖传入 report 中原有的变量行，不增加不存在的模板字段。

## DGB 重量和图签标签

`DeepGrooveBallBearingServer.SetCADTextValue` 的`W01` 外圈、`W02` 内圈、`W04/W04Z` 单球/球组、`W07/W07Z` 半保持架/两半保持架、`W` 整体名义重量已按相应来源处理：

- 内/外圈 `CalculateWeight` 使用圈尺寸、沟道、圆角半径等公开 getter（长度 0.01 mm），仍使用原版 `7.8 g/cm³` 假设；必须有经过核实的倒角和沟道数据才填圈重和总重。
- `StampingCage.CalculateWeight` 中 `Dcp,Dc,dc,S` 为 **0.1 mm** getter，`Rc` 为 **0.01 mm** getter，材料和几何同原版经验公式；只适用于明确选用冲压保持架的路径。
- 单球 `W04` 在球径 0.001 mm getter 后进行 `Math.Round(mass,5)`；`W04Z` 为滚珠数量乘已经舍入的单球重量。
- 原版 DGB 的 `W09/W09Z` 在 `SetCADTextValue` 中被注释，且三类服务未自动赋值 `W16/W46`；这些字段维持未填状态，不伪造材质或重量数据。
- ACB / CRB 原版出图没有与 DGB 同等的全部 `W` 分支，不将 DGB 重量算法直接复用过去。

原始 DWG、SQLite 数据库、CSV、STEP/STL 和现有几何算法均未改动。CADImport/AutoCAD 的现场图签校核仍由 Windows 验收确认。

## CI 回归与验收

自动回归覆盖不同轴承类型、真实调用重载、缺表/缺系数、系数近似未命中、载荷和单位、工艺型保持架、DGB 圈重/半保持架质量与 `W04` 舍入边界，以及没有源码赋值的重量字段。
