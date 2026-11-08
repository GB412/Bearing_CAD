# PR-OPT-02：RoBAS ACB 多目标优化与用户确认

## 源码依据（用户提供的原版 RoBAS）
- `Core/BallBearing/AngularContactBallBearing/ACBOptimizer.cs`：
  `SetCoeffccient` 按 70/72/73 系列选 Kw 范围与 K2i/K2e；
  `CalcuBallNum` 根据球径和工程塑料/酚醛保持架材料估计球数；
  `Optimizer` 使用 BallDB 邻近 5 个离散球径 × 5 个球数 × 节圆 0.05 mm 网格；
  计算旋滚比、轴向刚度、额定动载荷、额定静载荷并按三权重评估。
- `Frm/Dialog/FrmBearingOptimizer.cs`：用户输入预载荷 Fa(N)，原版默认权重旋滚比 0.3、轴向刚度 0.3、Cr 0.4。
- `Resource/BallDB.csv` 和 `Resource/球轴承零件相关系数.csv`：必须真实读取；`gamma=Math.Round(Dw*cos(alpha)/Dpw,2)` 必须准确匹配系数行。
- `Data/BearingType.db` 有表 `角接触球轴承型号目录`，但在用户给出的原版资源包中该表为空；因此不能声称型号标准公称 d/D/B 已得到原版目录验证。

## 功能合同
输入：初始 `{bearing_type,d,D,B,contact_angle_deg,cage_material,cage:null}`；
优化条件 `{model,accuracy_class,preload_n,weights:{spin_ratio,axial_stiffness,dynamic_load}}`。
预载荷单独属于优化工况，不属于已存在的 CAD 请求必需几何参数。
三项权重均为 0～1，合计 1。接触角当前只开放可查明源规则的 15、25、40 度，型号只开放 70/72/73 源系列。

输出：最多 5 组 Dw/Z/Dpw、内外圈沟道曲率、四肩部直径、旋滚比/Ka/Cr/Cor 和加权评分。
`candidate_only=true` 且 `applied=false`；必须用户点击确认才应用到现有三维/二维共用参数表。
原版优化将最优候选自动写回；本工程保留用户确认这道门槛。

## 需要特别解释的两项差异
1. 原版 `GetIndexEvaluationFunctionMax` 把归一化旋滚比按较大者给高分（不是通常理解的“越小越好”）。本 PR 为实现原版行为，维持其评分方向并发出警告，不声称工程意义已经认可；需老师确认后才能宣布目标合理。
2. 原版 ACBOptimizer 只求内外圈的一组挡边直径。当前 Bearing_CAD 的三维 CAD 使用非对称四挡边字段。因此 `_candidate_geometry` 在保留原版计算的单边主要直径基础上，增加明确标注的 0.15Dw 次级挡边偏置作为 CAD **适配构型**，并加保守几何检查。这部分不是师兄源码的直接同值迁移，也不是制造设计规范；仍须 OCCT 实体和实机工程图验证。

## 原版保持架当前不做虚假迁移
原版 `StraightPocketCage` 的内部/外部导向间隙与目前 CAD 窗孔保持架结构不同，不能直接把旧保持架套到新滚动体组合上。本 PR 初始设计必须 `cage=null`，用户需要先关闭保持架。后续可经专门的 ACB 保持架几何审核 PR 再接通。

## 验收
- `tests_v2/test_robas_acb_optimization.py`：源规则及 Ka(Fa) 立方根关系、材料球数、有效候选、权重/型号/角度边界、系数精确匹配、非静默修改。
- `tests_v2/test_robas_acb_optimizer_api.py`：同源 API 门禁、无资源降级和真正的 OCCT 几何回归。
- `tests-browser/rolling-acb-optimization.spec.js`：无用户确认不写 CAD；确认后同一套 ACB 参数进入 2D/3D；更改预载荷/保持架触发失效或拒绝。
- 在 Windows 实机需提供 7008、25°、合法预载荷及完整 RoBAS 原版资源的结果截图、STEP 和 DXF，并逐张核对图签/肩部/保持架字段。GitHub Linux CI 不等于这一步。

本 PR 叠放在 PR #88 之上，不能在 PR #88 尚未合并时独立合并 main。先合并 #88，再将本 PR 目标分支改为 main，执行完整 CI 并进入验收。
