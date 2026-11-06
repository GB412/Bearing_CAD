# PR-2D-06：技术条件分支与几何公差 getter 精度对齐

## 本 PR 处理的已证实缺口

### 1. 外圈技术条件的直径系列默认列

原版 `DataControl.GetOuterRaceTechnicalCondition`（`DataControl.cs:1401–1407`）的 `VDdp` 选择为：

- 系列 9：SQL 行索引 2；
- 系列 0/1：索引 3；
- 系列 2/3/4：索引 4；
- 其他系列：索引 5。

Python 原 `drawing_legacy_technical._outer` 没有实现最后的默认分支，系列 7/8 会得到空值。已补上索引 5。总图外圈 getter 原先已有对应默认列，未重复改写。

### 2. 公式公差和几何文字的原版 getter 精度

源码核对依据：

- DGB / ACB / CRB 的 `BearingInsideDia`、`BearingOutsideDia` getter：以米为内部存储，返回 `Math.Round(value * 1000, 2)`。
- `BallRoller.BallDiameter`（`BallRoller.cs:47–52`）：返回 `Math.Round(value * 1000, 3)`。
- CRB 的 `CylinderRoller.RollerLength`（`CylinderRoller.cs:53–58`）：返回 0.01 mm；`CylinderRoller.RollerDiameter`（`CylinderRoller.cs:46–51`）直接返回米值乘 1000，不做舍入。
- `MachineElement.cs:593–684`：沟道直径和位置公差按传入 getter 值分段；`MachineElement.cs:701–832`：挡边直径及沟道曲率半径公差。
- ACB 的 `AngularContactBallBearing.cs:313–416`：角接触沟道位置公差、锁口高度下偏差和轴承宽度偏差。
- ACB `CalculateLockHeight`（`AngularContactBallBearing.cs:279–310`）使用 `BearingInsideDia`、`BallRoller.BallDiameter` 与 `Geometry.OuterRaceGrooveDiameter` 的公开 getter 值；锁口高度最终再经 `LockHeight` 的 0.01 mm getter。

已修正：
- DGB/ACB/CRB 的沟道直径、位置和挡边公差分段使用原版直径 getter；
- DGB/ACB 沟道曲率半径公差使用球径 0.001 mm getter；
- 传入图纸的沟道直径、沟道位置、沟道半径和挡边名义文字先经过相应几何 getter，再按原版格式输出；
- ACB 的宽度偏差、锁口高度、沟道位置与锁口高度下偏差使用原版 getter 精度；
- CRB 的宽度、内径、外径、滚子长度和内圈沟道位置使用原版 0.01 mm getter；滚子直径保持原始 double，因为 `SetCADTextValue` 使用的是 `CylinderRoller.RollerDiameter`，不是 `CRBOptimizer.RollerDiameter` 的 0.0001 mm getter。

所有舍入仅作用于二维文字/公差计算；不改用户输入、OCCT B-Rep、STEP/STL、DWG、SQLite 或 CSV。

## 测试

新增回归覆盖：
- DGB/ACB/CRB 外圈技术条件的 7/8 系列默认列；
- 30.004 mm 与 50.005 mm 处 getter 先舍入再选择公差；
- 球径 6.0005 mm 的 0.001 mm getter 边界；
- ACB 锁口高度中 d / Dw getter 的调用精度；
- CRB 滚子直径使用未舍入 `CylinderRoller` getter 的 E1/E2 边界。

## 不在本 PR 范围

不修改原版 SQLite 数据，不添加缺少源依据的数值；不迁移额定载荷/重量公式；不重新绘制 DWG；不改变三维几何、优化器或 CADImport 桥接器。Windows CADImport / AutoCAD 真实 DXF 仍需用户最终验收。
