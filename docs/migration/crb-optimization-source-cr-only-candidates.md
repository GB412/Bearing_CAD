# PR-OPT-03：圆柱滚子轴承 CRB 的源代码忠实候选搜索

## 目标与事实边界

**用户希望三类轴承都支持优化。** 但师兄原版 `CRBOptimizer.cs` 的 `CalcuRadialStiffness()` 硬编码返回 `Kr=0`，其 `GetIndexEvaluationFunctionMax()` 又将归一化 Kr 与未经归一化的 Cr(N) 混合打分。因此直接把原版算法叫做可靠的“Cr/Kr 双目标优化”会产生误导。

本 PR 不凭空补写 Kr 经验式，交付的是**有 RoBAS 原版数据和公式支持的 Cr 优先候选推荐**。设置 `objective=dynamic_load_only`，结果的 `radial_stiffness_source_units=null`，警告明确说明 Kr 未实现。用户能从几组候选中选结构，但不能把它当作完整力学校核。

## 实际原版依据

来自用户上传的 `RoBAS(1).zip`：
- `Core/RollerBearing/CylinderRollerBreaing/CRBOptimizer.cs`：`SetCoeffccient` 的 Kwmin/Kwmax、`DetermineRollerDiameter`、`DetermineRollerLength`、`CalcuRollerNum`、`Optimizer` 网格。
- 同文件 `CalcuRadialDynamicLoad`：`Cr=1.89*fc*Lw^(7/9)*Z^(3/4)*Dw^(29/27)`。
- 同文件 `CalcuRadialStaticLoad`：`Cor=21.6*Z*Lw*Dw`。
- 原版 `Resource/CylinderRollerDiameterDB.csv`、`CylinderRollerDB.csv`、`圆柱滚子轴承相关系数.csv`。

**与二维图纸区别：** 原版 CRB 优化器的 `SearchCoeffcient(gamma,out fc)` 读圆柱滚子系数 CSV；原版二维图纸 Server 的 `SetCADTextValue` 却读继承自 BaseOptimizer 的球轴承系数 CSV。这两个路径在原版就不同，不应该合并“统一”为一个无出处公式；候选提供来源 CSV 的 SHA256。

## 输入和输出

初始输入：当前 d/D/B、N/NU/NJ/NF/NUP 构型、明确的径向几何净距/轴向端部净距/挡边宽度、已有用户选择的滚子轮廓及其倒角/凸度、保持架关闭。型号和精度等级从现有二维图纸设置中取得，如 `NU208`、`P5`。缺少原版权威型号目录时，只验证 N-family 前缀与 CAD 构型是否一致，不宣称型号 d/D/B 已按标准认证。

搜索：以 0.3(D−d) 为中心在原版离散直径 CSV 中选相邻 5 档、数量在原版估计数量左右各 2 档、长度从同直径 CSV 的标准长度中选不超过原版最大长度规则的候选，节圆按照 C# 的 0.05 mm 网格在 [0.5(D+d),0.515(D+d)] 搜索；按原版系数计算 Cr 和 Cor。

候选：完整的现有 CAD 请求参数（Dw/Lw/Z/Dpw、挡边顶径、净距、构型、滚子轮廓等）以及 Cr/Cor 和来源 SHA256。为了避免五个候选只有节圆 0.05mm 微小差异，对 Dw/Lw/Z 同组去重后最多展示五种结构，依 Cr 从大到小排序。

保持架现阶段暂不复用：滚子数量/长度改变后旧 `cylindrical_window` 几何不能直接套用，需要用户先关闭保持架，确认候选后另行设置。

## 哪些行为不是原版完全一致？

- 原版 `DetermineRollerLength` 首行比较基准有可能返回未在长度表中列出的初始目标；本 PR 始终返回同滚子直径的真实标准长度，记录保护性修复。
- 当前 Bearing_CAD 用显式 `radial_clearance_mm` 构造滚道间隙，保持架和滚子可选 crowned/chamfered 端部属于 CAD 扩展；不能把三维实体称为原版完全同一几何。
- 内外挡边顶径采用源 CRBOptimizer 的系数，按现有 CAD 包络约束过滤，不是制造规范公差校验。
- 原版径向刚度函数返回零，归一化/评分不可靠；本 PR 用 `Cr/max(Cr)` 作为**单目标相对评分**，不是原版原样的双目标评分，也不能声称已完成刚度优化。
- 仍然没有真实工作载荷、转速、润滑与拟静力求解；候选 Cr 不是实际工况的寿命/载荷分布校核结果。

## 验收矩阵
- `tests_v2/test_robas_crb_optimization.py`：原版系数/Cr/Cor 公式、型号与构型一致性、前置参数最小化、五种挡边构型、Kr 不可用与单目标、缺源拒绝。
- `tests_v2/test_robas_crb_optimizer_api.py`：端点、同源防护、缺资源降级、真正的 NU/NUP OCCT 候选 B-Rep。
- `tests-browser/rolling-crb-optimization.spec.js`：候选仅预览、用户确认才更新 2D/3D 共用设计、原始型号或几何改变时失效、旧保持架不允许直接复用。
- Windows 实机：真实资源、CADImport、AutoCAD、NUP 活动挡圈人工核查。Linux CI 不能代替此验收。

本 PR 只开发 CRB 优化，不修改原版 RoBAS 的 DWG/SQLite/CSV，亦不开发 RoBAS_v2.exe 拟静力学模块。完成后由用户审核授权再合并。
