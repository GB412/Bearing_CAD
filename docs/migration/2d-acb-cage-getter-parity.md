# PR-2D-03：角接触球保持架尺寸舍入与公差分界

## 源码对照

用户提供的 `RoBAS(1).zip`：

- `BearingModel/Cage/BaseCage.cs:23-42`：外径、内径和宽度 getter 保留 2 位小数（毫米）。
- `BearingModel/Cage/StraightPocketCage.cs:56-77`：兜孔直径 getter 1 位、保持架节圆及兜孔间距 getter 3 位（毫米）。
- `StraightPocketCage.cs:39-50,252-255`：兜孔间距通过 **读取已舍入的 OutsideDiameter 属性** 再计算，随后再经间距 getter 保留 3 位。
- `AngularContactBallBearingServer.cs:1077-1179`：`Dcp`、`C_`、`Dc`、`Dc1`、`Bc`、`Bca`、`Deltac` 直接取前述 getter；直径和宽度公差采用这些 getter 的值进入分段函数。
- `BallRoller.cs:47-51`：钢球直径 getter 保留 3 位，影响兜孔上偏差的 18 mm 分界。

## 本次修改

在已有原版尺寸及公差函数上加回 getter 的两阶段计算精度；例如保持架外径实际为 `50.004 mm` 时，原版 getter 返回 `50.00 mm`，外径公差查询应采用 `50.00` 对应的 `0.062 mm`，而不是原始 `50.004` 对应的 `0.074 mm`。

`C_` 先用 0.01 mm 的外径 getter 求间距，再以 0.001 mm 格式给出标注。不修改用户选定的 OCCT 实体尺寸，只统一原版 **二维标注值及其公差输入来源**。

## 保留边界

- 只对 `straight_pocket` 保持架适用；没有保持架不臆造源默认尺寸。
- 原版 `StraightPocketCage.DetermineCharmfer` 有 `e_` 候选规则，但现有 OCCT 实体没有实际倒角，所以 **不填** `e_` 与上下偏差。
- 对超出原版公差查表范围的直径、宽度保留未填，不用 0 代替。
- 其他角接触球沟道/锁高及完整技术条件还有单独复核工作；本 PR 不声称全部二维变量已完结。
- 没有重画 DWG、修改 CADImport、修改 SQLite 或改变 STEP/STL/B-Rep 实体。
- CADImport/AutoCAD Windows 实机、逐张 DXF 标注核对及制造审核仍需人工验收。

## 缓存身份与新标注

已导出的 DXF/SVG bundle 是不可变缓存。对角接触球增加
`acb_cage_getter_precision=robas.public-getters.v1` 作为缓存键的一部分；
即使原版文字刚好相同，新的 `source_getter_precision_decimals`
来源诊断也不会被旧 `drawing_manifest.json` 隐藏。
深沟球和圆柱滚子的缓存标识不变，无需删除本地历史成果。

## 自动测试

`python -m pytest tests_v2/test_drawing_legacy_acb_cage.py tests_v2/test_drawing_legacy_dimensions.py -q`

新增测试覆盖精确舍入、跨越公差分段端点、已有标注格式、未定义表项及保留未填的倒角。

## Windows 验收建议

根据实际三维 cage 尺寸生成角接触球原版 DWG 四张 DXF，在保持架图 `cage.dxf` 核对
`Dcp`、`C_`、`Dc`、`Dc1`、`Bc`、`Bca`、`Deltac` 的数值与
`Dc_Lower`、`Dc1_Lower`、`Bc_Lower`、`Deltac_Upper` 的符号。
不应出现无实体来源的 `e_` 标注。
