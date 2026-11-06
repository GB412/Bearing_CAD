# PR-2D-02 — 深沟球原版二维变量与挡边几何来源审查

## 目标和边界

本轮核对了用户上传的原始 `RoBAS(1).zip`：
`Controls/DeepGrooveBallServer/DeepGrooveBallBearingServer.cs:SetCADTextValue()`
（原版约 592–1180 行）、`Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs:53–99`，
以及 `Core/BallBearing/BallGeometry.cs` 对毫米尺寸的两位小数 getter。

**不是重新绘制 DWG**。仍由原版 SQLite 变量表、CADImport 逐项 `CADText.Text`
替换完成 DXF；未验证的制造公差、额定载荷和缺失源数据不得伪填。

## 原版 68 个直接变量分支的范围

| 类别 | 原版直接分支数 | 当前处理入口 | 特别边界 |
|---|---:|---|---|
| 型号与基本尺寸 | 6 | `drawing_variables.prepare_variables` | 型号需与 d/D/B 交叉审查 |
| Cr/Cor 载荷 | 2 | `drawing_legacy_ratings` | CSV 系数未命中时不可视为有效设计额定值 |
| 四组倒角及上下偏差 | 20 | `drawing_legacy_chamfer` | 必须实际选择倒角并命中 SQLite |
| 沟道、挡边及其公差 | 15 | `drawing_legacy_design` + `drawing_legacy_dimensions` | 名义公式不等于任意 OCCT 实体 |
| 冲压保持架尺寸、公差 | 16 | `drawing_legacy_design` + `drawing_legacy_dimensions` | 简化展示保持架不冒充原版冲压笼 |
| W 重量字段 | 9 | `drawing_legacy_dimensions` + `drawing_legacy_design` | 原版 `W09/W09Z` 分支未赋值，保留未填 |
| 合计 | **68** | | 原版直接条件分支，不等于全数据库变量数 |

除这些直接分支外，原版循环还从 DataControl 的粗糙度、径向游隙、
宽度公差、内外圈技术条件数据库表读取变量。该类数据由
`drawing_standard_fill` 和 `drawing_legacy_technical` 单独处理；
不能把 68 当作全图必须填满的标注数。

## 本轮源公式补充

RoBAS `DGBGeometry` 的源值（毫米）：

- `Dpw = (d + D) / 2`
- `di = Dpw - Dw`
- `De = Dpw + Dw + Gr`（原版经验 C0 游隙，需可用且适用）
- `d2 = di + k·Dw`、`Dd2 = De - k·Dw`
- `k=0.35` 当 `0 < d <= 25 mm`，其余正内径使用 `k=0.40`
- 原版侧挡边值以 `BallGeometry` getter 精确到 `0.01 mm`，而
  `SetCADTextValue` 输出时 `Dd2/d2` 用 `f1` 标注，公差通过
  `DetermineSidewallDiameterTolerance` 分段表形成。

新代码为当前设计计算原版理论 `Dd2/d2` 参考值，并写入
`legacy_design_evidence.original_source_shoulder_mm` 与
`original_source_shoulder_matches_cad`。
**只有原版节圆和实际三维挡肩同时匹配时才把源值作为标注来源。**
不匹配则保持实际 OCCT 的 `inner_shoulder_d_mm` /
`outer_shoulder_d_mm` 作为二维名义值，同时加入明确来源警告，
不偷偷把模型修成原版尺寸。选择 C2/C3/C4/C5 等非原版 C0 条件时，
不会使用原版 C0 外沟道尺寸推算 `Dd2`。

举例：d40/D68/Dpw54/Dw8、Gr0.013 → 原版 `d2=49.20`、
`Dd2=58.81`。如果实际 CAD 挡肩是 47.2 / 60.8，则图纸保持
**47.2 / 60.8**，并报告原版几何差异；不能把 `49.2/58.81`
强行写入与当前实体不对应的 DXF。

## 本 PR 不声称完成的内容

- 不能由原版未赋值的 `W09/W09Z` 或没有公式的 `Dk/ZG` 虚构数值。
- 尚须按**最新** `drawing_manifest.json` 的每张图纸 `variable_diagnostics`
  实际命中项完成剩余变量复核。历史“56 个空变量”不是当前验收数字。
- Windows 授权 CADImport、AutoCAD 实际显示、公差/工艺审核仍由用户实机验收。
- `manufacturing_approved: false` 不变。

## 验收

1. `python -m pytest tests_v2/test_drawing_legacy_design.py tests_v2/test_drawing_legacy_dimensions.py -q`
2. 检查 25 mm 挡边系数分界；原版 40 mm 样例的 `49.20/58.81`。
3. 同尺寸但自定义 47.2/60.8 的 CAD，确认未被自动覆盖且诊断有警告。
4. 非 C0 游隙及自定义节圆时，确认不误称原版来源。
5. Windows 在 `drawing_manifest.json` 查看 `legacy_design_evidence`，再在四张 DXF 中校对 `Dd2/d2` 及公差。
