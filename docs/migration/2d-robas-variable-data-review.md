# RoBAS 2D 变量补全进度与证据

## 为什么不能把原始 56 个空值全部设为零

旧 `unfilled_database_variable_count` 统计的是整个 SQLite 变量表中未填的不同变量名，并不是当前 DWG 实际缺失的标注数。PR #62 新增每张图纸基于 CADImport `matched_keys` 的真实命中空值报告，避免把未使用数据库字段错误归为图纸缺陷。

原版 C# 的 `SetCADTextValue()` 先从轴承几何、保持架、材料重量和标准表取值，再把数据写入变量表，最后进行 DWG `CADText.Text` 精确替换。不能只移植 2D DWG 模板就期待全部变量自然有值。

## 本轮已接入的值

| 数据源 | 能够填写的字段 | 限制 |
| --- | --- | --- |
| `DataControl.GetRoughness`（原版 SQLite） | `@Dds`、`@Dde`、`@Dd`、`@ds`、`@di`、`@d` 以及滚子类型适用字段 | 需选定精度等级，数据库有匹配行 |
| `DataControl.GetWidthDeviation`（原版 SQLite） | `B_Upper`、`B_Lower` | 球轴承仅支持原版定义的系列 0/2/3；其他保留空值和警告 |
| `DataControl.GetRadialClearance`（原版 SQLite） | `Cmin`、`Cmax` | 用户必须明确选择 C2/C0/C3/C4/C5；没有选择不得猜测 |
| `DGBGeometry / DGBOptimizer` | `di`、`a`、适用时的 `De` | 使用当前设计的 Dw/Dpw/B，C0 近似径向游隙按 mm 单位换算；超出原版有效范围或用户另选游隙组时不冒充匹配 |
| `StampingCage` 与当前三维双半保持架参数 | `C_`、`C1_`、`Dcp`、`Dc`、`Dc1`、`S_`、`Rc`、`tc`、相应有来源的公差 | 只在选择 `stamping_double_half` 后填充；必须使用三维实例已经确认的尺寸，不把简化环缘保持架假装成冲压笼 |
| `StampingCage.CalculateWeight` | `W07`、`W07Z` | RoBAS 名义公式；不等于 OCCT 实体精确体积或实际材料校核 |
| `SingleRowDeepGroove{Inner,Outer}Race.CalculateWeight` | `W01`、`W02`；三种重量均存在时可继续形成 `W` | 必须指定原版可查的倒角，且原版 r/r8 资料完整、结果有限且为正；否则不自动填值 |

以上只补数据，不修改 RoBAS DWG 静态线条、不改变 CADImport 精确 TEXT 替换、不增加 2D/3D 几何相等门禁，也不自动认证制造图。

### 尚未擅自填的变量

`K_`、`K_Upper`、`K_Lower`、`rrc`、`W16`、`W46`、`ZG`、`@d2`、`@Dde` 等剩余项需逐项核对具体 DWG 和设计对象。**请以最新 manifest 的每张图纸实际命中空值为准**：有些变量虽然在数据库中为空，却并不出现在本次四张图中。

注意：RoBAS 的 `DGBGeometry` 采用内部以米为单位的字段，而 `DGBOptimizer` 游隙函数输出毫米。新 Python 模块统一按毫米处理并显式标注这个单位边界，不复制原版可能出现的混合单位错误。

## 本地验收

启动本地 CADImport 服务后，依次用相同设计参数生成：

1. 默认简化保持架：验证冲压笼专用字段仍未自动填写，且 manifest 有明确警告。
2. 双半冲压保持架：验证 `C_`、`C1_`、`Dc`、`Dc1`、`Dcp`、`S_`、`Rc`、`tc` 和名义半笼重量来自已确认参数。
3. 原版已明确的倒角参数：验证条件满足时 `W01`、`W02` 可计算；不满足时为空。
4. 原版图框和 AutoCAD 字体使用合法提供的 `HZTXT.SHX`；核对当前四张 DXF 与对应 SVG 的技术文字显示是否正常。

查看：`artifacts/cad-v2/drawings/<bundle_key>/drawing_manifest.json`。

关注 `unfilled_database_variable_count`（全库空项）、`unfilled_template_variable_count`（当前实际命中的不同空变量）、`unfilled_database_unused_names`（没有用到的数据库空项）、`legacy_design_evidence`（自动计算来源与限制）。

所有 `manufacturing_approved` 均保持 `false`，工程/公差专业审核应单独开展。
