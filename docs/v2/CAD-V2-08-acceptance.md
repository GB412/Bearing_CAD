# CAD-V2-08 圆柱滚子轴承建模：实施与验收

## 决策及源代码依据
- 参考 RoBAS 的 `CRBGeometry.cs`、`CylinderRollerBearing.cs:239–263` 和 `CylinderRoller.cs`，保留 N/NU/NJ/NF 的不同圈挡边，及滚子节圆阵列；不引入 Eyeshot/WinForms。
- RoBAS 的 NUP 绘制路径没有独立可分离挡圈；新实现的 NUP 是**内圈单挡边 + 独立活动挡圈 + 外圈双挡边**，活动挡圈单独构件，不与内圈融合。
- 全部几何输入显式且为 mm，不复用未审核的 RoBAS 优化器经验公式；圆柱滚子无冠形、倒角、详细保持架/兜孔、制造公差，属功能几何预览级。
- N/NU/NJ/NF/NUP 共五种构型，双圈和滚子用 Z 中面对齐；挡边由径向截面一次旋转生成闭合 OCCT 实体。

## V2 请求新增圆柱专属参数
`radial_clearance_mm`, `axial_clearance_mm`, `rib_width_mm`, `inner_rib_tip_d_mm`, `outer_rib_tip_d_mm`；
其余必填：`bore_d_mm`, `outside_d_mm`, `width_mm`, `roller_d_mm`,
`roller_length_mm`, `pitch_d_mm`, `roller_count`, `configuration`。
所有滚子共享一个 B-Rep 定义，实例由 `translation_mm` 定位；滚子轴沿 Z。
`configuration` 可选 N、NU、NJ、NF、NUP；此阶段不接受 cage 参数。

## 几何约束
- 轴承内孔半径 < 内圈滚道半径 < 内挡边顶端半径 < 外挡边顶端半径 < 外圈滚道半径 < 外径半径。
- 两圈滚道到滚子之间均保留显式正径向间隙（该量是简化 CAD 几何净距，**不等于设计径向游隙的工程定义**）。
- 滚子长度/端部轴向间隙必须与双挡边共存；相邻滚子弦长需超过滚子直径。
- 所有零件须有效且无非预期相交；NUP 活动挡圈与内圈是分离实体。
- 所有尺寸有限且大于零，数量最大 256。API 另将实例数量限定 64（服务预算而非轴承标准）。

## 构型表
| 形式 | 内圈一体挡边 | 外圈一体挡边 | 独立挡圈 |
|---|---|---|---|
| N | 左右 | 无 | 无 |
| NU | 无 | 左右 | 无 |
| NJ | 左 | 左右 | 无 |
| NF | 左右 | 左 | 无 |
| NUP | 左 + 右端活动挡圈 | 左右 | 有 |

“左”指 Z<0，“右”指 Z>0；镜像方向将来可作为显式额外版本输入，而不能默默交换。

## 验收
- 五构型分别建立独立有效 Solid、STEP 导出与回读、三组几何尺度；
- API 对 NUP 成功生成与下载 STEP/manifest，质量报告标注 `CAGE_OMITTED`；
- 深沟球旧请求仍然有效，旧 CAD 工作台及旧 CAD CI 不退化；
- 固定 CadQuery 2.5.2 的 GitHub Actions 新增测试真实执行并通过后，方可宣称 PR 达到合并条件；
- 该 PR 完成后仅推送 **feature/cad-v2-08-cylindrical-roller** 和创建待审 PR，**不合并 main**。

## 非目标
本 PR 不移植尚无足够校核数据的圆柱滚子保持架；前端要展示五种构型需要扩展滚动工作台的轴承类型选择和动态参数表，不应拿深沟球输入伪造滚子模型。详细 UI 接入可后续单独 PR 完成。
