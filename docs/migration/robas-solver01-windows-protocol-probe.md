# PR-SOLVER-01：RoBAS_v2.exe Windows 真实求解器可行性验证

## 一、已经确认的原版事实（源文件直接核对）

用户提供的源包：`RoBAS(1).zip`、`RoBAS_Resources.zip`。

- `RoBAS/Core/BallBearing/BallBearingAnalysis.cs`：`generateStaticAnalysisInputs()` 输出 **43** 行 `'rec ...'` 记录，其中第 11 行为 `rec 5A`。
- `RoBAS/Core/RollerBearing/CylinderRollerBreaing/CylinderBearingAnalysis.cs`：静力输入 **44** 行；第 11/12 行分别为 `rec 5B.1`、`rec 5B.2`。
- 两份源码的 `generateAnalysisInputTxt()` 都写到原版应用 `exe/DATA.txt`；`Solve()` 均以 `exe` 为工作目录执行 `RoBAS_v2.exe`，再从 `exe/OUT.txt` 读出结果。
- 源枚举 `eAnalysisType` 实际开放的模式是 **拟静力学 = -1**；其余动力分支未形成可用的正式闭环。本 PR 只校验 `Mode=-1`。
- 原资源 ZIP **仅包含二进制 exe，不包含任何可作为黄金数值案例的 `DATA.txt` 或 `OUT.txt`**。所以不能在 Linux CI 中假装真实求解已通过。
- 源包中 `RoBAS_v2.exe` 大小 **4,605,952 bytes**，PE 架构 **x86**，SHA-256：
  `0449dbade9f97da768961e7cd8af3277b8a6fbf2bf8a2b2c9c23784caac11829`

## 二、本 PR 做到什么（最小化）

只新增一个**本地命令行**诊断工具 `bearing_cad/robas_solver_probe.py`，不会引入新的 HTTP 执行端点、后台队列、Agent 工作流、数据库、前端页面，也不会改动已有三类 CAD 模型/二维图纸。

1. `inspect`：只读验证用户电脑上的原版 x86 PE 和精确原版 SHA-256；验证用户从**原版 RoBAS 软件实际产生**的静力 `DATA.txt` 的 43/44 条 `rec` 标签、先后顺序和 `Mode=-1`。
2. `run`：限 Windows，将验证过的 exe 和 DATA.txt **复制**到一次性的独立输出子目录后启动；原版 `exe` 和用户原始 DATA.txt 保持只读不修改；设置等待上限并保存隔离运行结果。
3. 检查进程退出状态和 `OUT.txt` 是否生成非空，记录 `OUT.txt`、`PRINT.txt`、`a0_Final` 的大小和 SHA-256，写出 `solver_probe_report.json`。
4. 即使进程退出 0 且 `OUT.txt` 存在，也只报告 `OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF`。**求解器是否收敛、接触应力数值是否正确、输入单位是否一致，本阶段均不作结论。**
5. 默认拒绝签名与原版 ZIP 不一致的可执行程序；无 Windows 环境不能真实运行 EXE。CI 使用一个由 Python 构造的**假 x86 PE 文件和模拟进程**验证隔离/失败处理；绝不把模拟输出描述成真实求解。

## 三、Windows 本地验收命令

先在安装有原版 RoBAS 的 Windows 上运行原版程序，创建一个**合法拟静力工况**并执行，让原版软件生成自己的 `DATA.txt`。不要自行手写或杜撰载荷、材料和润滑数值。将源 `exe/DATA.txt` **复制**到独立位置，例如 `D:\\RoBAS-Test\\DATA-ball.txt`。

以本地 `bearing-cad02` 环境和 `RoBAS_Resources` 资源目录为例：

```powershell
cd "D:\RotorStudio\Bearing_CAD\Bearing_CAD"
conda activate bearing-cad02
git fetch origin
git worktree add --detach "..\Bearing_CAD_SOLVER01" origin/feat/robas-solver01-windows-protocol-probe
cd "..\Bearing_CAD_SOLVER01"

$resources = "D:\你的资源目录\RoBAS_Resources"
$inputFile = "D:\RoBAS-Test\DATA-ball.txt"

python -m bearing_cad.robas_solver_probe inspect `
  --resources "$resources" --input "$inputFile" --family ball

python -m bearing_cad.robas_solver_probe run `
  --resources "$resources" --input "$inputFile" --family ball `
  --out ".\artifacts\solver-probe" --timeout 300
```

圆柱滚子案例使用 `--family roller`，且输入必须来自 **`CylinderBearingAnalysis.cs` 对应的原版圆柱滚子算例**，不能拿球轴承输入混用。

运行完成后，在 `artifacts/solver-probe/run-<唯一编号>/solver_probe_report.json` 中查看执行路径、原版数据 SHA、EXE SHA、进程状态、`OUT.txt` 等结果证据。若运行成功，请保留原版 RoBAS 的同一算例结果，以便下一阶段做数值对照。

若原版软件本机无法运行，或缺少 `DATA.txt` 示例，这一阶段只允许宣布 **源码协议审查 + 本地模拟 runner 测试通过**，不能宣布 EXE 真实求解已跑通。**不要把二进制 exe、原版私有资料或实际工况测试文件提交到公开 GitHub 仓库。**

## 四、下一 PR 的准入条件

`PR-SOLVER-02` 才实现从**用户确认的 Bearing_CAD 设计 + 实际工况（载荷/转速/材料/润滑/温度）**生成完整的 43/44 行 `DATA.txt`，并核验数值、单位、字段顺序。必须先有最少一套原版生成的真实 DATA/OUT 比对案例，且此 PR 的 `run` 能在授权 Windows 上得到可解析结果。

**PR-SOLVER-03** 再解析接触力、应力、角度、油膜厚度等并显示曲线；不能仅凭 OUT.txt 存在就声称求解正确。

## 五、验收分层

- **CODE_IMPLEMENTED**：本 PR 包含 CLI、预检、输出证据、失败分类、单测。
- **CI_PASSED**：Python fake PE/fake runner 和全部现有项目 CI 通过；不执行实际商业求解器。
- **WINDOWS_EXE_EXECUTED**：用户实际执行原版 EXE，记录退出码和 OUT.txt。
- **SOURCE_RESULT_COMPARED**：真实 OUT.txt 与原版 RoBAS 同算例数值对比（不属于本 PR）。
- **ENGINEERING_APPROVED**：专业人员审核计算物理适用性（不属于本 PR）。

保留各状态之间的界限，不虚构“已经移植完整拟静力学分析”。
