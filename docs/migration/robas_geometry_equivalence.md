# RoBAS ↔ Bearing_CAD 三维几何迁移基线（3D-MIG-01）

本文件的证据是用户提供的 `RoBAS.zip` 静态源码（SHA-256 `69b39ec937bcc942d223601995c7279573c629d81c652e56a3146b4f2c95d23d`）与现有 Python OCCT 模型。RoBAS 的商业 Eyeshot 环境未运行，因此**不能声称两边 STEP 体积/拓扑等价**。

## 真实绘图调用路径而不是推测的几何默认值

| 对比项 | 可核查 RoBAS 路径（`RoBAS/` 相对目录和行号） | 当前 Python | 当前结论 |
|---|---|---|---|
| 深沟球节圆 | `Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs:57`：`(D+d)/2`；`DeepGrooveBallBearing.cs:62` 标量构造：`(d+d)/2` | `contracts.py` 明确 `pitch_d_mm` | **INTENTIONAL_FIX**；不移植矛盾的默认式 |
| 深沟球球数 | `DGBGeometry.cs:58` 与 `DeepGrooveBallBearing.cs:63`：`(int)(186/(2 asin(Dw/Dpw) /π*180))+1` | 显式整数；几何检查相邻球不重叠 | **NOT_MIGRATED**；186 来源不明 |
| 深沟球沟半径 | `DGBGeometry.cs:60–61` `fi=.51 fe=.53`；`DeepGrooveBallBearing.cs:65–70` 标量默认 `fi=.52 fe=.54` | 明确输入内/外沟半径 | **NEW_IMPLEMENTATION**；不同调用路径不可混算 |
| 球/滚子阵列 | `BearingModel/Roller/BallRoller.cs:64–95` 和 `CylinderRoller.cs:67–101` | `geometry.py:circular_positions` | **LEGACY_EQUIVALENT（解析位置规则）**，不是实体等价 |
| 圆柱挡边 | `Core/RollerBearing/CylinderRollerBreaing/CylinderRollerBearing.cs:239–263` | `cylindrical_roller.py:_CONFIGURATIONS` | **NEW_IMPLEMENTATION（五种构型）**；NUP 活动圈是主动新增 |
| 圆柱窗孔笼 | `BearingModel/Cage/CylinderPocketCage.cs:124–160`，环形笼体减去 Z 个圆柱窗口 | 当前缺失 | **NOT_MIGRATED**，下一 PR 恢复 |
| 角接触单位 | `Core/BallBearing/AngularContactBallBearing/ACBGeometry.cs:64–79` 对 `alpha` 直接 Sin/Cos；`AngularContactBallBearing.cs:448–463` 绘图入口 Deg2Rad | `angular_contact.py:_raceway_centres` 度→弧度一次 | **INTENTIONAL_FIX**；不恢复不明角度路径 |
| 角接触截面 | `BearingModel/Race/InnerRace/SingleRowAngularContactInnerRace.cs:380–400`；`OuterRace/SingleRowAngularContactOuterRace.cs:303–328` 绘图：3° 锥体+环面 | 阶梯截面+轴向偏移环面 | **UNVERIFIED**；禁止称几何等价或未经审核自动替换 |
| 角接触沟轴向位置 | `ACBGeometry.cs:65,79` 算了 GroovePosition；但两个 `Draw3DRace` 的 `CreateTorus` 未见应用平移 | 现 Python 有显式 (R,Z) 偏移 | **NEW_IMPLEMENTATION**，专业审查前不变更生产几何 |
| 深沟球冲压半笼 | `BearingModel/Cage/StampingCage.cs:199–305`：双半笼+球形切窗+铆钉 | `deep_groove.py` 简化连桥笼 | **NOT_MIGRATED**，不得把预览模型称为旧版冲压笼 |
| 角接触窗孔笼 | `BearingModel/Cage/StraightPocketCage.cs:322–361` | 无保持架 | **NOT_MIGRATED** |

## 同参数可复核数值，非旧版 Solid 测量

手工夹具 `d=40,D=68,Dw=8,Dpw=54,Z=11,alpha=25°`，长度均以 mm 记录。
- 两个旧深沟球节圆表达式给 **54** 和 **40 mm**；其旧经验球数式分别给 **11** 和 **9**。新契约显式设节圆 **54**。
- 旧 `DGBGeometry` 的内外沟半径：**4.08/4.24 mm**，旧标量构造的内外沟半径：**4.16/4.32 mm**，新 demo 为 **4.30/4.50 mm**。
- 同一 `alpha=25` 在旧 ACB 计算类直接作为三角函数参数，与绘图入口先转角度的路径数值不一致，不能将任一组当成经审核的产品结构。
- Python 当前角接触圆截面中心满足 `hypot(Δr,Δz)=groove_radius−ball_radius`，解析层可证明设计名义角；这**不是**与 Eyeshot 路径实体等价的证明。

## 测试及后续门槛
`python -m unittest discover -s tests_v2 -p 'test_*.py' -v` 包括 `test_migration_reference.py` 的旧路径数值差异、三个 builder 的装配实例与位置。原有 B-Rep/STEP 单测继续回归。

后续 PR 先移植圆柱滚子窗孔保持架并独立验证环体穿孔、桥厚、与滚子的间隙、STEP roundtrip。深沟球 Stamp 两半笼与角接触 StraightPocketCage 需另立 PR；3° 锥面必须有明确的图纸/同参数 Eyeshot 输出作为几何决策证据。

**未运行旧 Eyeshot CAD 软件，旧实体体积、真实端部结构与详细制造规范标记 UNVERIFIED。**
