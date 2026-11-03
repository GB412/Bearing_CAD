# 给 Codex 的首个执行任务：CAD-V2-00 基线冻结与 RoBAS 源码追溯

> 使用前提：将 `RoBAS.zip` 仅放在本地工作目录可读取的位置；未经师兄或课题组授权，不要把 RoBAS 完整源代码、商业依赖、二进制项目文件提交到公开 GitHub 仓库。

## 可直接复制给 Codex 的任务

你是本仓库 `GB412/Bearing_CAD` 的 CAD 系统重构负责人。现在执行 **CAD-V2-00：技术冻结、RoBAS 源码追溯及迁移规则审计**。本 PR **不写新的滚动轴承实体生成器，不修改旧用户界面，不重构多 Agent 主系统**。

### 项目背景

旧 `Bearing_CAD` 是基于滑动轴承的 AI 生成演示项目，核心 `cad02_pipeline.py`、`cad_workbench_drawing.py`、`viewer.js` 都与 `housing/bushing/shaft` 三个零件耦合。目标是建设新的 Python+CadQuery+OCCT 参数化轴承 CAD 核心，迁移 RoBAS 中的深沟球轴承、圆柱滚子轴承、角接触球轴承建模算法，后续接入多 Agent 系统。RoBAS 是 C# / Eyeshot v12 / WinForms，压缩包缺失相关 NetLib 外部工程，不能假定原程序可正常构建运行。

### 要做的工作

1. 从 `main` 最新版本创建 `feature/cad-v2-00-audit` 分支，记录基线 commit SHA。确认当前 CI 和可执行的本地测试命令；尽可能运行且记录原始结果，包括缺失依赖而跳过的情况。
2. 检查以下 RoBAS 路径：
   - `Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs`、`DeepGrooveBallBearing.cs`
   - `Core/RollerBearing/CylinderRollerBreaing/CRBGeometry.cs`、`CylinderRollerBearing.cs`
   - `Core/BallBearing/AngularContactBallBearing/ACBGeometry.cs`、`AngularContactBallBearing.cs`
   - `BearingModel/Race/InnerRace/`、`BearingModel/Race/OuterRace/`、`BearingModel/Roller/`、`BearingModel/Cage/`
   - 仅在必要时追踪 `*Optimizer.cs`、`BaseGeometry.cs`、`RollerGeometry.cs`、`BallGeometry.cs`、`Utility/*` 中的被调用规则。
3. 写 `docs/v2/source_traceability.md`：三条 `Plot3DModel()` 到每个实体生成方法的完整调用链；C# 类型及公式 → 新 Python 模块建议；字段单位（源码内部/外部）、引用位置、规则用途、风险标记。
4. 写 `docs/v2/geometry_rules_register.md`：每条建模所需公式与硬编码系数（包括 Dw、Dpw、Z、fi/fe、GrooveRadius、SidewallDia、Cage 参数），列出具体源文件/行号、算法说明、取值范围、当前可信状态和待验证用例。
5. 必须重点定位并核查两个问题：`DeepGrooveBallBearing.cs` 中 `Dpw=0.5*(d+d)` 与 `DGBGeometry.cs` 中计算方式不一致；`ACBGeometry.cs` 三角函数是否遗漏度→弧度转换。另核对 `BallRoller.cs` 与其他属性中的 m/mm 隐式换算。
6. 写 `docs/v2/legacy_assessment.md`：旧 `Bearing_CAD` 的复用/废弃清单；区分已由测试验证的能力、只通过静态检查的能力和未验证事项。
7. 写 `docs/v2/architecture_decisions.md`：确认采用独立 `bearing_cad/` 包、新旧隔离、统一毫米/度、Z 轴、独立 Parts、STEP 为权威输出、Three.js 仅显示、审批状态只由主系统所有。
8. 根据实际原代码与潜在许可证限制，提出 PR-01 的最小契约 API 草案和测试夹具列表。**不要提前实现 PR-01 代码。**

### 禁止事项

- 不在本 PR 实现 `DeepGrooveBearingBuilder`，不引入新的 CAD API 框架。
- 不修改 `main` 上的旧滑动轴承行为，不删除现有演示代码。
- 不拷贝 RoBAS 整个源码或 Eyeshot DLL 到公开仓库；知识产权状态不明确时，只记路径、行为概述和小范围必要公式。
- 不对未实际执行的测试宣称“通过”，不把随意估计的工程几何参数冒充标准值。
- 不扩展到统一二维工程图或多 Agent 集成。

### 必须提交的证据

- 所有新增文档和必要的审计脚本（若确有必要）。
- `docs/v2/CAD-V2-00-acceptance.md`：基线 SHA、分支 SHA、执行的命令和终端结果、风险、结论、PR-01 输入条件。
- PR 描述包含：本次只做了什么、没有做什么、潜在授权问题、原始 C# 无法编译的限制、下一 PR 的具体输入。

### 完成判据

- 三类轴承每一条实体创建链路都能从入口追溯到 C# 建模类和方法。
- 所有长/角字段的实际单位已记录，至少两个历史可疑公式有明确调查结论或阻断风险项。
- 旧项目当前的可运行/不可运行功能已分类，未改变旧业务行为。
- PR 生成并提供分支、commit、测试记录和 PR 链接；如果没有写权限，仅提交可审阅的本地 diff，不要虚构 GitHub PR。

**执行流程：先读取并复述边界 → 检查仓库与源码 → 输出审计表 → 必要时少量辅助测试 → 本地自检 → 提交 feature 分支 → 创建 PR → 交付验收报告。不要自行进入 CAD-V2-01，待当前 PR 审核通过后继续。**
