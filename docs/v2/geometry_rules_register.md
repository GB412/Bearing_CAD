# 几何参数与公式风险登记表

本表登记 RoBAS 源码可观察到的实现行为及需核验问题。公式未获得独立工程来源或数值验证前只能视作待审算法，不能写为推荐设计规则。行号以 `BearingCAD_Demo/.reference/RoBAS/` 当前源码为准。

| ID | 参数/规则 | 源码位置与实现 | 单位/含义审查 | 风险与后续处置 |
|---|---|---|---|---|
| G-01 | 基础 D/d/B | DGB `DGBGeometry.cs:53–58`、ACB `ACBGeometry.cs:46–55`、CRB `CRBGeometry.cs:53–59`；构造输入内部看似以 m 运算，属性 getter 多乘 1000 输出 mm | 内部 SI 长度为 m；公开属性与 UI 多为 mm，但无类型级单位区分 | 新 API 只接受显式 `*_mm`；核心几何统一 mm（CadQuery 默认 mm），适配层只做一次校验/转换；禁止在模型中混用隐式裸 double 单位 |
| G-02 | DGB 滚动体直径 | `DGBGeometry.cs:56`：`DetermineRollerDiameter(0.3*(D-d)*1000)/1000`；另一构造 `DeepGrooveBallBearing.cs:61`：`...*100)/100` | 两种比例因子使输入单位不同，需追踪优化器函数期望值；默认 `BallRoller()` `BallRoller.cs:29–33` 设置 `.0019050` m，而 DGB 默认几何球径 `.019050` m | 默认 Roller 与 Geometry 值相差 10 倍；重建前必须确认真实调用分支，不要从默认值推断标准球径 |
| G-03 | DGB 节圆直径 | DGBGeometry `DGBGeometry.cs:57`: `(outsideDia+insideDia)/2`；显式构造 `DeepGrooveBallBearing.cs:62`: `(d+d)/2` | 前者是外/内径中径，后者退化为 d | 高优先级疑点；核对调用路径与参数单位后做独立解析几何校验，保留原始值作为审计 fixture，不静默替换 |
| G-04 | DGB 球数 | `DGBGeometry.cs:58` 与 `DeepGrooveBallBearing.cs:63` 使用 `186/(2*asin(Dw/Dpw)/π*180)+1` | 弧度转角度的表达式等价于完整角宽的 degree 换算，但前置 186 的来源/覆盖角未知 | 可能造成球数过密、球互相干涉或兜孔过近；需检查 `2*asin(Dw/Dpw)`、相邻球净距及滚道位置，注明 Z 的整数舍入策略和最小间隙 |
| G-05 | CRB 球数/球径/长度 | `CRBGeometry.cs:53–73`：直径由 `0.3*(D-d)` 经优化器选取；长度由 D/B 传给优化器；Z 由 `CalcuRollerNum` | 计算经多次 m↔mm 转换，且长度/直径值 property 显示有 round | 追踪优化器的输入输出单位及精度，避免 round 后用于 B-Rep；不同 N/NU/NJ/NUP/NF 使用同一派生路径的合理性需验证 |
| G-06 | ACB 接触角单位 | `AngularContactBallBearing.cs:41–44` 默认 `contactAngular=25` 并原样传 `ACBGeometry`；`ACBGeometry.cs:48,64–65,78–79` 直接 `sin/cos(alpha)`；Plot3D `AngularContactBallBearing.cs:462–463` 才调用 `Deg2Rad(alpha)` | 属性名/界面说明为度；几何类 trig 期望弧度，但构造器无转换 | 严重单位边界歧义：25 rad 与 25° 导致不同沟径/位置。CAD-V2 必须以 `contact_angle_deg` schema 输入，在唯一 helper 中转弧度，并加入已知角度定值测试；旧公式先记录，不判定正确值 |
| G-07 | ACB 沟道派生 | `ACBGeometry.cs:63–79` 以曲率 0.525/0.515、`cos/sin(alpha)` 派生沟半径、沟径、沟位置；race scalar constructors `SingleRowAngularContact*Race.cs:109–121,129–141` 另有公式 | 同一概念存在 Geometry 和标量两套实现；参数角度沿调用链可能不同 | 使用哪种构造重载、单位和符号方向须逐条确认；通过几何中心关系/切触距离做约束检查，不从绘图外观认证接触角 |
| G-08 | DGB 沟道半径/位置/沟径 | `DGBGeometry.cs:60–82`：`Re=fe*Dw`, `Ri=fi*Dw`; 沟位置 `B/2`; 外沟径 `Dpw+Dw+Gr`; 内沟径 `Dpw-Dw`; race scalar constructors对应 `SingleRowDeepGroove*Race.cs:91–108` | DGBGeometry 用 m；Race 属性 set 通常换算 mm→m，构造参数存在裸 double | 明确各重载预期的参数单位；把径向游隙 Gr 纳入统一几何关系，检查沟底壁厚、沟圆弧和球接触位置；沟曲率 0.51/0.53 来源未注明 |
| G-09 | 挡边直径 | DGB `DGBGeometry.cs:67–81`、ACB `ACBGeometry.cs:67–86` 按 d 阈值取 `沟径 ± 0.35/0.40Dw`；CRB `CRBGeometry.cs:72–73` 使用优化器 | 比例值直接影响沟边截面/滚动体保持 | 阈值边界可能离散跳变，存在薄壁/沟道穿透风险；使用 section/profile 自动测最小壁厚和边缘有效材料，来源需注明 |
| G-10 | CRB 沟径及侧挡组合 | `CRBGeometry.cs:61–90`：沟径 `Dpw±Dw`，构型 N/NU/else 设置不同的圈内/外径；绘图开关 `CylinderRollerBearing.cs:239–263` | enum 与实体映射分开维护 | 枚举只涵盖绘图映射；NUP 未生成独立挡圈，实际轴向定位功能可能不完整；逐构型验证实体及零件数，未支持构型明确拒绝 |
| G-11 | Roller 阵列位置 | `BallRoller.cs:64–95`、`CylinderRoller.cs:67–101`：中心平移到 `pitchDiameter/2`，角度 `2πi/Z`，转轴 Z | 角度是 rad；其循环为 `< Z`，位置规则清晰 | 检查与两圈沟道中心、装配原点和法向一致；验证球/滚子间隙、体积交叠和边界偏置；每一实例需保有稳定 ID |
| G-12 | Sphere/Straight 兜孔数量 | `SpherePocketCage.cs:78–86` 与 `StraightPocketCage.cs:349–357` 预先切一次，再循环 `i<=pocketNum` | 周期阵列需恰好 Z 个独立位置 | 当前是 Z+1 个切除且 0° 重复；Boolean 重复切可能产生冗余/数值不稳。新实现只生成 `range(Z)`，测试拓扑/孔数与相邻孔最小材料桥 |
| G-13 | 笼尺寸/间隙经验式 | `StraightPocketCage.cs:39–50,113–129`：`1.004Dw+0.12`、Factor、guide gap、宽度修正；`CylinderPocketCage.cs:34–43` 直径/长度 1.02 倍 | 0.12/0.5 等常数若以 mm 用，但方法内部多使用 m，需沿 property setter 查证 | 潜在单位错配和尺寸倒置；缺少公差、材料/制造方法依据。每公式记录来源、目标间隙、适用尺寸范围，否则只作为可选受审参数 |
| G-14 | Stamping cage | `StampingCage.cs:161–187,199–305`：型号分支决定板厚/宽度/兜深，两个半笼球兜、铆钉几何及布尔切除 | 代码混合模型型号字符串、长度单位、由球数导出角间距 | 高复杂度和硬编码，不作为首个 MVP；先分离纯参数公式并测试，再决定是否仅复用设计意图 |
| G-15 | B-Rep 相切/接触 | RoBAS Draw3D 调用只添加实体，无可检索的装配碰撞/拓扑验证链 | 目测模型显示不能证明有效、无自交或满足间隙 | 新引擎分层报告精确体积、validity、bounding box、预期接触/间隙、非预期间隙和干涉；使用尺度相关容差并区分接触容差与设计间隙 |
| G-16 | 轴向基准与坐标 | RoBAS 滚动体构造以 Z 轴作转轴、滚动体沿 Z 建立；Race/Cage 通常沿 Z 宽度居中 | 不同 UI 绘图方法及轴线/原点一致性需确认 | 新契约固定轴线 Z、宽度中面 Z=0、节圆在 XY 平面、长度 mm、角度 degree 输入；每零件 transform 显式保存 |

## 公式审查结论

当前最重要的不是决定某条公式“正确”，而是把它变成可验证的候选规则。先核查来源、单位、调用重载和适用条件，再通过解析尺寸断言、有效 B-Rep、实际孔/挡边数量、体积与包围盒、装配干涉/间隙和 STEP 回读验证。任何只靠截图或无报错绘制的结论都不构成几何验收。
