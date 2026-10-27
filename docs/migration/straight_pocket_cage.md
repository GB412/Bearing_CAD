# 3D-MIG-03：RoBAS 角接触球 StraightPocketCage 径向窗孔迁移

## RoBAS 证据
`RoBAS/BearingModel/Cage/StraightPocketCage.cs:322–361` 在内外圆柱差集得到环体后，用**轴线沿 Y（径向）的圆柱切刀**在节圆上均布球窗。原代码在循环前先切一次，并用 `for (i <= pocketNum)` 再切除，导致同一角度切孔重复。新实现按 `range(Z)` 正好切除 Z 次，不复制重复布尔操作。

## 本次实际迁移
- 新增 `cage.kind = straight_pocket`，只允许 `rolling.angular_contact_ball` 使用。`inner_d_mm`、`outside_d_mm`、`width_mm`、`pocket_clearance_mm` 为**显式几何参数**，只沿用窗口结构逻辑。
- 原 C# 的经验窗孔 `1.004*Dw+0.12`、笼外径和导向间隙推导没有通过设计标准核查，因此**没有照搬**。本版窗口圆柱直径和径向贯穿长度均设为 `ball_d + 2 * pocket_clearance_mm`。这不同于原版尺寸推导，不应称为 1:1 等价。
- 支持 15°/25°/40° 的角接触球非对称圈体+滚动体+1 件窗孔保持架；检查笼内外径处于挡肩间、套住节圆、窗孔切穿笼壁但不切破轴向连接圈、不与其他窗孔相交。
- 每个滚动体位置对应一个窗孔；检查保持架封闭有效、无非预期穿透、STEP 文件中**14 个实体**有效，产物清单状态 `STRAIGHT_POCKET_CAGE`，升级生成器版本避免旧缓存混用。
- 无笼已有 angular/deep/cylindrical 请求继续兼容；不改变旧滑动轴承代码。

## 测试及限制
`tests_v2/test_straight_pocket_cage.py` 检查三种接触角下窗孔/桥位置、BRepCheck 与真实 STEP 全件回读，以及参数异常和缓存隔离。GitHub CAD-V2/旧 CAD 工作流全绿方可合并。

**仍未解决**：RoBAS Stamp 双半笼/铆钉、原角接触圈体 3° 锥面与现有阶梯轮廓的工程等价性、旧 Eyeshot 实体的独立比对。网页参数输入的笼种选择暂未开放，功能先通过 CAD Python/HTTP 契约与导出提供。此阶段不宣称制造级轴承产品。
