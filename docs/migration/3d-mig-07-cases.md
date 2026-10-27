# 3D-MIG-07A · RoBAS 三维结构对照基线

## 为什么先做 07A

现有三类轴承和 RoBAS 衍生保持架都能生成真实 B-Rep/STEP；但目前唯一可复核的 RoBAS 来源是 **C# 静态源码**，用户尚未提供可以确认参数与调用路径的 Eyeshot 导出 STEP。无法仅凭 `STEP roundtrip`、几何拓扑有效或零件数量一致，宣称与原 Eyeshot 模型一致。

本 PR **只增加对照证据，不修改轴承几何和 API**。同时保留两条并行的真实性边界：

- 旧源码：路径、单位、构造函数分支和解析方程等，可核查；但不是实测实体体积。
- 新 CAD：从已提交的 JSON 测试夹具，运行 CadQuery/OCCT、实际 STEP 导出与回读，测量零件体积、全装配 bbox、滚动体节圆半径/相位，以及已有 `geometry_quality.json` 的误差。
- 原 Eyeshot B-Rep：**NOT_AVAILABLE / UNVERIFIED**。此字段不能由新系统的有效实体自动填充。

## 七个固定基准样例

| 案例 ID | 输入 | 几何与检查要点 | 期望实例 |
|---|---|---|---:|
| `dgb_no_cage` | 深沟球，d40/D68/B15，11 球 | 双构造器节圆/沟曲率矛盾，滚动体均布 | 13 |
| `dgb_stamped` | 同规格 + 冲压双半笼、球兜及 11 铆钉 | 两片半笼、铆钉半相位、零件实例独立 | 26 |
| `crb_NU_window` | 圆柱 NU + 窗孔笼，d40/D68/B18，11 滚子 | 内外挡边、滚子节圆和窗孔 | 14 |
| `crb_NUP_window` | 圆柱 NUP + 窗孔笼 | 活动挡圈独立零件和窗孔笼 | 15 |
| `acb_15deg` | 角接触 15°、无笼 | 解析接触角、非对称沟道 | 13 |
| `acb_25deg_window` | 角接触 25°、径向窗孔笼 | 11 球及笼窗孔模型 | 14 |
| `acb_40deg` | 角接触 40°、无笼 | 解析接触角、非对称沟道 | 13 |

以上全部为人工构造的**几何测试夹具**，不是厂家标准型号，也不是经过授权/批准的制造图。

## 文件和操作

- `tests_v2/fixtures/robas_3d_cases.json`：保存七种明确参数、原 C# 源文件位置、期望构件 ID 和实例数。旧版 C# 路径保留原始拼写。
- `bearing_cad/migration_baseline.py`：运行现有 `generate_bundle` 生成 STEP、STL、设计快照、几何质量报告；额外输出 `comparison.json`（结构化结果）和 `comparison.md`（可读表格）。不另行开发 CAD 内核。
- `tests_v2/test_migration_baseline.py`：测试七案例来源和覆盖范围、DGB 两个节圆/曲率调用路径、角度单位差异、单案例真实 STEP 回读/报告重复生成和缺失旧 STEP 时必须保持未验证。
- `.github/workflows/cad-v2.yml`：完整七案例在固定 CadQuery 2.5.2 环境实际执行，上传**仅 JSON/Markdown** 的 GitHub Actions Artifact。完整 STEP 保存在执行机器构建目录，不提交巨型 CAD 二进制至 Git。

本地在与 `environment-v2.yml` 一致的 CadQuery Python 环境中运行：

```bash
python -m unittest discover -s tests_v2 -p 'test_*.py' -v
python -m bearing_cad.migration_baseline --output build/migration-07a
```

查看 `build/migration-07a/comparison.json`、`comparison.md`。每个案例完整生成的 CAD 成果位于 `build/migration-07a/bundles/`。重复运行应使用内容寻址缓存且对照文本保持相同内容。

## 解析差异与证据状态

- **深沟球**：C# `DGBGeometry.cs:57` 与标量构造路径 `DeepGrooveBallBearing.cs:62` 用不同节圆表达式，得到 54 vs 40 mm；`DGBGeometry` 默认 `fi=.51, fe=.53` 与标量构造 `fi=.52, fe=.54` 对相同球径给出不同沟半径。两个路径绝不拼接成所谓唯一旧版模型。
- **角接触球**：某些旧 C# 路径可能直接将数值 25 输入三角函数，另有 `Deg2Rad` 入口，旧 `3°` 锥面与当前阶梯截面结构不同；07A 仅捕获疑点，不修补现有有效 B-Rep。
- **圆柱滚子**：新 NUP 独立活动挡圈属于几何层级上的设计变化，不能写成原版已存在的独立 Eyeshot 零件。
- **保持架**：迁移的具体环/窗孔/双半笼三维构造方法已经完成，但老的装配尺寸推导规则、真实实体差异仍不能据此认定为等价。

## 07A 完成门槛 / 07B 外部依赖

1. 七组固定 JSON 案例有可追溯的源码调用路径，不混用冲突 C# 构造器。
2. 每例真实 B-Rep → STEP 回读成功；记录实例数、部件体积、整体包围尺寸、节圆和相位，以及当前导出质量指标。
3. 相同请求与相同 CadQuery 环境重复运行得到相同报告内容。**不固定 STEP 文件字节哈希**。
4. GitHub CAD-V2、CAD-01/02/03 与 Workbench 工作流全部通过。
5. 保持原版 STEP 缺失字段 `NOT_AVAILABLE` 和实体等价结论 `UNVERIFIED`，不能因为第 4 条通过而标记等价。

07B 启动条件是取得师兄 RoBAS 实际导出且附对应设计参数/调用路径的 STEP 或合法分享的等效 B-Rep 文件。没有时可先进行 08 的独立质量问题修复及 09 演示版本完善。

**特别注意：质量报告的 STEP 0.05% 交换限值和 RoBAS 几何等价阈值是两件完全不同的事。**
