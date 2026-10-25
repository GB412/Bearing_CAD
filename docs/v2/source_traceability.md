# RoBAS 源码追踪与三维建模调用链

审查日期：2026-10-26。引用基准为 `BearingCAD_Demo/.reference/RoBAS/`；所有结论是源码行为记录，不代表公式符合标准或几何已经通过验证。本阶段不复制、改写或执行 RoBAS 源码。

## 1. 调用链概览

RoBAS 的三维实现是 WinForms/Eyeshot 显示路径：轴承业务对象的 `Plot3DModel(Model)` 从几何参数取值、实例化圈/滚动体/保持架对象，再调用这些对象的 `Draw3D*` 方法，把 Eyeshot `Solid` 添加到 `Model`。没有发现独立 CAD 引擎、可复用的装配文件接口或与 UI 分离的中性 B-Rep API。迁移时应将业务参数和几何关系作为待审参考，不迁移这条 UI 渲染实现。

## 2. 深沟球轴承

入口：`Core/BallBearing/DeepGroveBallBearing/DeepGrooveBallBearing.cs`。

1. 默认构造函数第 28–52 行建立 `DGBGeometry(D=0.068 m,d=0.040 m,B=0.015 m)`，然后配置内外圈、`BallRoller`、`StampingCage` 和分析/优化对象。默认对象初始化并不等于 Plot3D 时所有几何都使用同一组值。
2. 参数构造函数第 59–74 行从 `Dd,d,B` 计算 `Dw`、`Dpw`、`Z`，硬编码 `fe=0.54, fi=0.52`，再创建两圈、钢球和冲压保持架。此处 `Dpw=0.5*(d+d)` 与 DGBGeometry 中点公式不一致，且构造参数单位边界未声明。
3. `Plot3DModel` 第 274–305 行读取 bearing 尺寸、曲率、Dw/节圆/球数；分别创建 `SingleRowDeepGrooveOuterRace`、`SingleRowDeepGrooveInnerRace`、`BallRoller`、`StampingCage`，随后按外圈、内圈、笼、球的顺序画入 Eyeshot。第 286–289 行取得的笼参数在随后构造中没有使用，改由 StampingCage 按型号再次推导。
4. 参数推导位于 `Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs` 第 53–82 行：`Dw=DetermineRollerDiameter(0.3*(D-d)*1000)/1000`；`Dpw=(D+d)/2`；球数为基于球径/节圆的角间距计算；滚道半径 `fe*Dw`、`fi*Dw`；外圈沟径含径向游隙 `Dpw+Dw+Gr`，内圈沟径 `Dpw-Dw`；沟位置 `B/2`；挡边直径按内径阈值采用 0.35 或 0.40 倍球径；保持架外/内径为挡边直径的 0.98/1.02 倍、宽度为 `0.95B`。
5. `BearingModel/Race/OuterRace/SingleRowDeepGrooveOuterRace.cs` 第 91–113、142–156 行和内圈对应文件第 88–108、133–150 行：构造器保存沟道 major/minor radius、沟径/沟位置、挡边尺寸；绘制以圆柱布尔形成环体，再用环面 (torus) 做沟道切除。需进一步以几何测试核实环面方位、沟道位置是否在当前构造分支实际生效。类同时保留独立的几何参数构造重载。
6. `BearingModel/Roller/BallRoller.cs` 第 38–43、64–95 行：用球径/节圆直径/数量初始化；球心先平移到节圆半径，再按 `2πi/Z` 绕 Z 轴阵列，各球作为独立 Solid 加入模型。
7. `BearingModel/Cage/StampingCage.cs` 第 161–187、199–225、226–305 行：由球径、节圆、球数、型号推导板厚/笼宽/兜深/铆钉尺寸；两半笼通过球兜切除和布尔组合形成，再按等角位置切铆钉孔/装配铆钉。方法中的诸多型号分支与经验常数应单独核证，不可整体翻译。

候选简化参考保持架 `SpherePocketCage.cs` 第 42–88 行由两个同轴圆柱差构成环体，以球体按节圆位置阵列后切兜。它先对初始球做一次差集，再执行 `i <= pocketNum` 循环，导致起始兜重复切除且执行 Z+1 次切除。

## 3. 圆柱滚子轴承

入口：`Core/RollerBearing/CylinderRollerBreaing/CylinderRollerBearing.cs`。

1. 构造函数第 21–38 行设定默认型号/尺寸和 N 构型，创建 `CRBGeometry(d,D,B,design)`。
2. `CRBGeometry.cs` 第 53–95 行按 `0.3*(D-d)` 选滚子直径；从 `CRBOptimizer.DetermineRollerLength` 得滚子长度；节圆取 `(D+d)/2`；滚子数交由优化器；滚道名义直径为 `Dpw±Dw`；挡边直径由优化器计算；N、NU 分支分别改变内外圈沟道/挡边边界；保持架外/内径用 `Dpw+0.5Dw`、`Dpw-0.45Dw`，宽度 `0.97B`。
3. `Plot3DModel` 第 200–272 行读取滚子/圈/笼参数，创建 `SingleRowCylinderOuterRace(Geometry)` 与 `SingleRowCylinderInnerRace(Geometry)`；第 239–263 行按 N/NU/NJ/NUP/NF 选择内外圈无挡边、单挡边、双挡边绘图方法；第 265–272 行创建滚子阵列和 `CylinderPocketCage` 并绘制。
4. 内外圈实体分支位于 `BearingModel/Race/{InnerRace,OuterRace}/SingleRowCylinder*Race.cs`：各自暴露 no/one/double sidewall 绘图方法；其中挡边由不同圆柱段组合/布尔形成。准确构型应以每个方法的实际尺寸与构造顺序为准，不能仅凭枚举名推断实体差异。
5. `BearingModel/Roller/CylinderRoller.cs` 第 36–43、67–101 行：构造滚子直径/长度/节圆/数量；圆柱轴向居中、中心平移到半节圆半径，按 `2πi/Z` 阵列。
6. `BearingModel/Cage/CylinderPocketCage.cs` 第 34–43、124–157 行：构造笼体环形毛坯，以略大于滚子的圆柱按节圆位置阵列切除窗孔。倍率 1.02 是明确几何间隙假设，但缺少公差来源说明。

限制：Plot3D 中计算的 `orGrooveDepth/orGrooveWidth/irGrooveDepth/irGrooveWidth` 位于第 211–219 行，但 `SingleRowCylinder*Race(Geometry)` 构造路径并不把这些局部值传入；需要核实最终槽型由几何对象还是 draw overload 负责。NUP 被映射为内外圈双挡边，但调用链未显示单独挡圈零件，模型可能只是简化外观，不能视为 NUP 完整标准结构。

## 4. 角接触球轴承

入口：`Core/BallBearing/AngularContactBallBearing/AngularContactBallBearing.cs`。

1. 默认构造第 31–56 行将名义角 `25` 传给 `new ACBGeometry(..., contactAngular)`，并默认选 `StraightPocketCage`。
2. `ACBGeometry.cs` 第 46–94 行将参数 `alpha` 直接写入 `Alpha` 并在 `Sin/Cos` 公式中使用；球径、节圆、球数和曲率由此派生；外/内圈沟径与轴向位置随 alpha 变化，挡边与笼尺寸按阈值/比例取值。源码没有在构造器边界显式进行 degree-to-radian 转换。
3. `Plot3DModel` 第 448–471 行读取 `BearingWidth`、Dw、Dpw、Z 和接触角；构造内外圈时调用 `MyMath.Deg2Rad(alpha)`，随后创建钢球和 `StraightPocketCage` 并绘制。这意味着参数构造时 ACBGeometry 的 trig 参数与绘圈时参数的角度单位路径可能不同。
4. `SingleRowAngularContactInnerRace.cs` 第 109–162 行和 OuterRace 对应第 129–171 行包含沟道公式、曲率、沟位置及侧肩构造。Geometry 重载与标量重载存在不同公式/缺省值，例如 Geometry 重载内圈沟半径来自 `0.515*Dw`，沟径 `Dpw-Dw`，而标量重载使用 alpha 相关公式；必须确定 Plot3D 实际选用哪条重载并比对其期望单位。
5. 保持架使用 `StraightPocketCage.cs` 第 39–50、322–360 行：沟槽/导向间隙、笼内外径、宽度和兜间厚度由比例/经验关系推导；绘图环体以横向圆柱切球兜，随后循环 `i <= pocketNum`，存在 Z+1 切除/重复首孔问题。

## 5. 共用实体基础与依赖

- `BearingModel/Race/InnerRace/BaseInnerRace.cs`、`Race/OuterRace/BaseOuterRace.cs`、`Roller/BaseRoller.cs`、`Cage/BaseCage.cs` 定义尺寸属性与 `Draw3D*` 抽象方法；这些类型把模型数据和 Eyeshot 输出绑定。
- 建模直接依赖 `devDept.Eyeshot` Solid/Model API、RoBAS 优化器/枚举、GlobalSetting 颜色和 WinForms 业务对象。`RoBAS.csproj` 引用 Eyeshot v12（项目路径 `../packages/Eyeshot12.0.239.0`）。这形成商业库许可、运行时和版本绑定风险。
- 钢球/滚子采用离散 Solid 实例阵列；轴承圈和笼多采用圆柱布尔、环面切除或逐件滚动体布尔。并未发现拓扑检查、干涉报告、STEP 导出或统一 manifest 由 Plot3D 调用链负责。

## 6. 必须在后续验证的追踪结论

1. 对三个构造器/Plot3D 两条路径建立参数表，逐项确认 mm/m 和 degree/radian；当前命名与 get/set 转换不足以单凭变量名确认所有边界。
2. 复现深沟球两种 Dpw 推导差异，核实 `DGBGeometry` 和 `DeepGrooveBallBearing(string,...)` 在真实 UI 路径中各自何时调用。
3. 用 CAD 查询而不是截图验证 race torus 几何、保持架孔数、N/NU/NJ/NF/NUP 挡边实体、圆柱滚子端部形状、角接触沟道位置。
4. 对 Eyeshot 的 bool 结果、容差、空 Solid、单实体/多实体、共面/相切行为查版本 API 与许可；不能据 UI 中“显示成功”推断实体有效。
