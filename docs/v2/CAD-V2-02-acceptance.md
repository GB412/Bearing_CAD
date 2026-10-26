# CAD-V2-02 精确几何原语及拓扑检查验收

## 本 PR 实现

- `bearing_cad/geometry.py`：毫米制、Z 轴的环体、封闭二维径向截面旋转、球体、平端圆柱滚子、节圆实例位置。
- `bearing_cad/geometry_checks.py`：单实体检查（OCCT BRepCheck、封闭 Shell、实体数量、体积和尺寸），两个有效实体的精确相交体积。
- `tests_v2/test_geometry_primitives.py`：环体和截面几何体积/包围盒验证、解析球/柱体积、圆周坐标、干涉、非法参数。
- **不实现**深沟球内外沟道、真实轴承装配、保持架、CAD API 或前端；这些属于后续 PR。

## 开发环境自测

`python -m unittest discover -s tests_v2 -p 'test_*.py' -v`：10 tests OK，包含此前 PR-01 的真实 STEP 探针。
开发环境 CadQuery 2.8.0 / OCP 7.9.3.1。远端 CI 固定 CadQuery 2.5.2，必须待实际执行后单独验收。
`inspect_solid` 的封闭判定基于实体的实际 Shell；不能直接依赖顶层 Solid 的 Closed 属性。

## 进入 CAD-V2-03 前的条件

- 本 PR 的 V2 kernel CI 及所有旧 CAD 工作流通过；
- 首个深沟球示例的完整明确尺寸/节圆/球径/沟道坐标要经过数学约束检查，不能默认采用 RoBAS 未审公式；
- 第三方 CAD STEP 装配检查和带语义的 assembly 导出在后续建模/导出 PR 验收。

**本 PR 完成的是通用几何基础，不代表滚动轴承建模已经完成。**
