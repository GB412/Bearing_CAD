# 3D-MIG-02 · RoBAS 圆柱滚子窗孔保持架迁移

## 源头和边界
- C# 源：`RoBAS/BearingModel/Cage/CylinderPocketCage.cs:124–160`：内外圆柱差集形成环坯；圆柱切刀沿 Z 轴，放置于 `Dpw/2`，严格 `i < PocketNum` 旋转并依次布尔差集。
- 新实现：`bearing_cad/cages.py:cylindrical_window_cage` 使用 CadQuery/OCCT 保留**环形 B-Rep 减去 Z 个轴向圆柱窗口**的几何方法。没有复制 C# 代码/Eyeshot 库。
- 明确不同：原构造器用 `1.02*cyDia` 和 `1.02*cyLen` 派生窗口尺寸，缺少工程来源。本版本要求一个明确的 `pocket_clearance_mm`，窗口直径和长度均为 `roller_size + 2 * allowance`，不能声称原窗口尺寸完全等价；这是三维概念间隙，不是制造公差。
- 初始几何夹具：轴承 d40/D68/B18，滚子 d8/L12，节圆54，Z=11；保持架内/外径52.6/55.4，轴向宽16，窗口半径余量0.15 mm。**这些不是产品选型或厂家推荐尺寸。**

## 功能
- 契约维持 `bearing-cad.request.v1`：圆柱滚子可选 `cage: {kind: cylindrical_window, inner_d_mm, outside_d_mm, width_mm, pocket_clearance_mm}`。默认不提供 cage 时仍原样生成无笼模型，兼容已有请求。
- N/NU/NJ/NF/NUP 五种构型均可添加真正的独立 cage 部件；NUP 仍保留独立 `loose_rib`。
- 保持架径向位置必须介于内外挡边顶径间且包络节圆；窗孔不重叠，轴向两端必须保留连接圈，超出轴承宽度则拒绝。
- 使用 OCCT BRepCheck 检查整件连通的封闭实体，并与内圈、外圈、滚子以及可选 NUP 挡圈做精确相交体积检查。
- 导出 STEP/STL 后回读全部实体，manifest 用 `CYLINDRICAL_WINDOW_CAGE` 区别于旧深沟球 `SIMPLIFIED_CAGE`；生成器版本更新以避免旧缓存与新几何同键。

## 测试
`tests_v2/test_cylindrical_cage.py`：逐构型窗口中心穿透采样、球间连接桥、Z 方向两端残留连接圈、装配实例数、碰撞检查；NU/NUP 的真实 STEP 回读/文件签名、非法几何拒绝、无笼旧请求回归。全部随现有 GitHub CAD-V2 CI 固定 CadQuery 环境执行。

## 仍需解决
- 此阶段只完成圆柱滚子窗孔保持架，**并非整个 RoBAS 保持架移植完成**；深沟球双半笼铆钉与角接触直线窗孔仍需后续 PR。未完成 FreeCAD 人工图形检查。
- 网页 UI 目前对圆柱保持架输入保持关闭；本 PR 提供 Python/HTTP 契约与 CAD 输出，统一工作台控件可在后续小 PR 启用，不能声称网页已能设置笼体。
- 没有原 Eyeshot 实体输出，**不宣称新旧笼体体积完全相等**。环结构和窗孔布尔策略属于方法继承，参数策略属于主动安全差异。
