# CAD-V2-03 深沟球轴承核心几何验收

本 PR 提供基于 RoBAS 建模思路的**精确 B-Rep 功能级模型**：内圈、外圈、两条环形沟道及 Z 颗钢球。使用 Python/CadQuery/OCCT，而非复制 C# / Eyeshot 代码。

## 设计和输入边界

- 在深沟球 schema 中额外要求显式 `inner_shoulder_d_mm`、`outer_shoulder_d_mm`，不使用未经复核的 RoBAS 肩高经验公式。
- 结构坐标 Z 为轴承轴线，滚动体分布于 XY 平面的节圆上；沟道利用旋转圆截面形成环面切削体。
- 保持架**未实现**，正式输出应明确标记 `CAGE_OMITTED`；本 PR 不提供通用生产级导出服务或二维工程图。
- 测试尺寸 (d=40, D=68, B=15, ball d=8, PCD=54, Z=11, inner/outer groove radii=4.3/4.5, shoulders=47.2/60.8 mm) 是**几何验证夹具**，不对应制造商认证的完整 6008 设计。
- 接触/间隙策略：拒绝正体积穿透；允许存在间隙，不提供预载、滚动体接触变形、真实游隙和寿命分析。
- 无密封、倒角、滚道表面粗糙度、公差；不能称为制造工程图。

## 本地测试

`python -m unittest discover -s tests_v2 -p 'test_*.py' -v`：共 12 项通过。测试涵盖 3 种几何缩放、B-Rep 有效性、13 件实例 STEP 导出并回读、球之间碰撞以及异常曲率拒绝；开发环境 CadQuery 2.8.0 / OCP 7.9.3.1。GitHub Actions 固定 CadQuery 2.5.2，须以远端结果再次验收。

## 下一步

CAD-V2-04 单独实现保持架；CAD-V2-05 实现规范化装配 STEP/网格、质量报告和产物追踪。完整 STEP 文件的第三方 GUI 软件检查目前未执行，不能将自动回读等同于独立 CAD 工程审查。
