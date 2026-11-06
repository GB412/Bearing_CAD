# PR-2D-05：三类轴承二维标准公差、游隙与粗糙度真实来源核对

## 适用范围与来源

本次逐行核对用户提供的 `RoBAS(1).zip` 和 `RoBAS_Resources.zip`（未将原版数据库添加进仓库）：

- `Core/BallBearing/DeepGroveBallBearing/DeepGrooveBallBearing.cs:100–120`、`Core/BallBearing/AngularContactBallBearing/AngularContactBallBearing.cs:83–103`、`Core/RollerBearing/CylinderRollerBreaing/CylinderRollerBearing.cs:70–90`：三类轴承的 `BearingInsideDia` 和 `BearingOutsideDia` 在 public getter 中都执行 `Math.Round(bearing... * 1000, 2)`，单位 mm。
- 三类 `*BearingServer.cs:SetCADTextValue` 使用这些 *已舍入* 的内径 d 查找 `GetRadialClearance`、`GetRoughness`、`GetWidthDeviation` 和内圈技术条件，使用 *已舍入* 的外径 D 查询外圈技术条件。
- `Utility/DataBase/DataControl.cs:809–1008`（游隙、粗糙度）、`1454–1519`（宽度偏差）：`WHERE d >= value LIMIT 1` 或 `WHERE 套圈直径 >= value LIMIT 1`，**没有 ORDER BY**；由文件行顺序决定第一条有效范围，不能改成最近邻、向下取整或按公差估算。
- 原版 `DGBData.db`、`ACBData.db`、`CRBData.db` 的 `游隙`、`轴承宽度公差`、`粗糙度表` / B/C/D/E/G 级粗糙度表。读取原版原始 SQLite，**不更改任何表数据**。

## 发现并修复的共性问题

现有 Python 的标准查表调用路径直接使用用户 CAD 数值，如 `d=30.004 mm`，原版 C# 则在调用前通过 public getter 得到 `30.00 mm`。在原版 SQLite 的公差区间恰好以 `d=30 mm` 为结束值时，未经舍入的 30.004 可能错误进入下一档。

现在三类轴承统一先恢复原版 **0.01 mm getter**，再使用此值独立查询三组真实源表；同时让原版四张技术条件表也使用同一 getter 语义。不会修改实际 OCCT B-Rep 或用户设计输入的原始数值。对于原始正尺寸在舍入后变 0 的输入，明确报错而不是查询到无效表行。

在 `standard_lookup_evidence` 增加：
- `lookup_diameter_mm`：真正用于查表的原版 getter 值；
- `source_range_upper_mm`：原版无排序 SQL 实际选中的第一条表行上界；
- 已有 `source`、`kind`、`accuracy_class` / `diameter_series` / `group` 原样保留。

这样可以核对名义尺寸、分段边界、选择组别和原版数据出处；任何越界、`--`、不适用值仍不能伪填，`manufacturing_approved=false` 不变。

## 三个原版 SQLite 的实测表上界（所选前几行）

| 库 | 游隙 d 上界 (mm) | 宽度公差 d 上界 (mm) | D 级粗糙度 套圈直径上界 (mm) |
|---|---|---|---|
| DGBData.db | 10,18,30,50,80 | 10,18,30,50,80 | 10,30,80,120 |
| ACBData.db | 6,10,18,24,30,40,50 | 10,18,30,50,80 | 10,30,80,120 |
| CRBData.db | 6,10,18,24,30,40,50 | 10,18,30,50,80 | 10,30,80,120 |

注意 CRB 的原版出图 `GetRoughness` 固定使用 `粗糙度表`，不随 P0/P5 等改变。这是原版 C# 的明确分支，不应该擅自改成 CRB 数据库里也存在的 `D级粗糙度表`。

## 已迁移的标准规则（本 PR 只补来源边界和可追溯性）

- C2/C0/C3/C4/C5：原版游隙表中十列，原始 μm 数值 /1000 变换为 mm。`--` 标记为未定义，不用 0 填。
- 球轴承 B/C/D/E/G 精度级粗糙度表与原版六列映射，圆柱滚子轴承 `粗糙度表` 十列映射。
- 球轴承宽度公差只对直径系列 0/2/3 有直接表列，圆柱滚子采用独立 B_Upper/B_Lower 列。
- 技术条件分段按内圈 d / 外圈 D 分开查询；其余分支映射仍属于之后的专项核验。

## 验收与未完成项

- `python -m pytest tests_v2/test_drawing_standards.py tests_v2/test_drawing_legacy_technical.py tests_v2/test_drawing_runner.py -q`；
- 对原版数据库与三个 Python 模拟库进行 30.004→30.00 与 30.006→30.01 的区间边界测试，确认来源行上界与 TEXT 内容；
- Windows CADImport 生成 DGB/ACB/CRB 四张 DXF，比较 `standard_lookup_evidence` 的来源上界、游隙组、宽度上下偏差和各粗糙度文本；
- `drawing_runner` 对三类轴承的不可变成果键增加该 getter 来源版本，使旧 manifest 不会遮蔽更正的标准值/来源记录；历史成果无须删除；
- 不修改原版 DWG、SQLite、CADImport、STEP/STL 和浏览器 UI，不声称已完成后续质量/额定载荷、全部技术条件和制造级 AutoCAD 验收。


## 复审增补：.NET Framework 的 0.005 mm 中点与缓存

独立代码审查发现：原版 C# 的 setter 先将用户毫米数值除以
1000 存储为 `double` 米，public getter 再乘以 1000，调用
`Math.Round(..., 2)`。原版运行时的 `Math.Round(double,2)` 对小尺寸
采用先乘 100、在浮点数上使用中点到偶数的整数舍入、再除以 100；
与 Python `round(value,2)` 在二进制表示下不总是相等。

因此本 PR 的补充修正将三类轴承的标准表/技术条件取值统一到一个
getters 函数：`(value_mm / 1000.0) * 1000.0`，
再 `round(getter_mm * 100.0) / 100.0`。仅用于二维查表，不修改
设计尺寸、三维 B-Rep、原版数据库和 DWG。交叉验证的典型输入：

| 输入 mm | 原版旧 .NET 行为 | Python 直接 round(value,2) |
|---|---:|---:|
| 30.004 | 30.00 | 30.00 |
| 30.006 | 30.01 | 30.01 |
| 50.005 | 50.00 | 50.01 |
| 2.675 | 2.68 | 2.67 |
| 0.015 | 0.02 | 0.01 |
| 0.005 | 0.00（拒绝无效查表直径） | 0.01 |

针对 50.005，已有三类合成库的游隙、宽度偏差、粗糙度及技术条件
查询回归；本次同时将不可变出图缓存来源版本从
`bearing-diameter.v1` 改为 `bearing-diameter.v2`。
原版实际 SQLite 数据尚需与 Windows CADImport/AutoCAD 生成的
DXF、manifest 一起审核；不能据此声明制造审核完成。

实现依据：原版三类轴承 public getter（本文件前述 C# 路径），
以及旧版 .NET Framework `Math.InternalRound(double,int,...)` 先缩放、
中点到偶数舍入、再缩回的实现。未来如更换原版运行时，请以同版
真实 C# 执行结果复核这些边界。
