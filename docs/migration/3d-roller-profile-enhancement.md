# 圆柱滚子端部轮廓：原版兼容和增强模式

原版 RoBAS `BearingModel/Roller/CylinderRoller.cs:Draw3DRoller()` 生成的是简单的 `Solid.CreateCylinder`。新代码的 `plain` 模式保持此建模行为；`chamfered` 和 `crowned` 模式是 **Bearing_CAD 新增工程 CAD 功能**，不是来自 RoBAS 的制造规格。

| 模式 | 后端字段 | 几何构造 |
| --- | --- | --- |
| plain | `roller_profile='plain'` | 无端部修形的直圆柱 |
| chamfered | `roller_end_chamfer_mm` | 两端对称 45° 倒角 |
| crowned | 倒角尺寸 + `roller_crown_relief_mm` | 按轴向二次径向卸荷构造的连续 B-spline 旋转曲面，兼有两端倒角 |

三维模型生成使用 CadQuery/OCCT 精确 B-Rep，输出 STEP/STL，并通过现有干涉与 STEP roundtrip 校核。设置表单中，`roller_crown_relief_mm` 是端部相对于滚子中央公称半径的径向减小量（不是直径减小量）。默认网页示例 `d=8mm, L=12mm, c=0.2mm, relief=0.02mm` 是演示参数，不是工业标准。

旧 API 请求不带新参数时仍生成普通圆柱。已明示的三维增强参数跟随请求哈希写入设计快照，不擅自修改二维 DWG 模板或技术标准。端部凸度曲线并非实际经过校核的对数修形，不能将其描述为对数凸度或承载能力优化；如后续需要载荷相关的修形，应移入独立设计/接触校核阶段。
