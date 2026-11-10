# 滚动轴承工作台拟静力学分析

先按 [本机分析 API 启动说明](robas-solver05-analysis-api.md#server-setup) 配置已审查的原版参考 DATA，再构建并运行现有工作台。

```powershell
npm run build
.\scripts\run_bearing_cad_with_robas.ps1 -SkipBuild
```

打开本机服务的 `/rolling.html`。没有分析配置时，三维、二维和优化仍使用现有服务。

## 页面操作

1. 选择轴承类型并编辑结构尺寸，或运行优化后点击「确认并应用此设计」。手动方案点击「确认当前设计」。已有依据的球数和沟曲率半径可切换到手动录入。ACB 如需使用分析参考配置的保持架材料，应主动将 CAD 材料设置为「不指定」并录入已核实的球数。
2. 生成三维模型。二维图纸仍通过现有原版 DWG 模板生成。图纸标签比对提交的设计快照哈希。图纸的模板、型号、精度及其他出图选项仍单独生效。
3. 打开「拟静力学分析」，选择服务器提供的配置。DGB 和 ACB 需要填写经核实的分析内圈外径。ACB 还须从当前设计的内外圈左右肩分别选择分析挡边。CRB N 型从 CAD 快照取几何。若 CAD 径向净距非零，需独立填写分析游隙。
4. 按原版 RoBAS 坐标输入 X/Y/Z 载荷、内外圈转速及需要的分析游隙。留空继承参考 DATA。运行完成后，「本次运行工况」列出各值的来源与生效值。如果后端报告参考几何差异，核对提示后可明确确认覆盖。
5. 查看接触载荷与应力曲线、内外圈接触表、扫速位移和刚度、功率损失、内部游隙，以及运行编号、来源和文件哈希。无效值标为「不可用」并保留原始标记。

球轴承显式 CAD 保持架和 ACB 显式 CAD 保持架材料尚未映射到原版分析。CRB 分析限 N 型直滚子。其余构型仍可按各自既有 CAD 能力生成模型。

## 版本和状态

- 确认记录保留在本次页面会话中。三维作业成功后，页面匹配作业编号、清单、设计请求和哈希。提交分析前从这个作业读取 `design_snapshot.json`，对原始字节重新计算 SHA-256。
- 编辑几何会清除确认和旧 CAD 关联。编辑分析几何、参考配置或运行工况会使当前结果转为历史。提交时记录版本，晚到的响应按原版本展示。页面保留最近一次结果，完整运行证据由本机 API 保存。
- 分析时禁止重复提交。界面显示后端的超时、忙碌和字段错误。结构化结果通过同次运行文件哈希验证后展示。退出码、支持分段的解析状态、指标有效性和收敛分别显示。
- 结果支持当前 RoBAS 格式中已核对的字段。没有独立收敛证据时，界面显示「未知」。

## 验证

公开浏览器测试覆盖表单、版本变更、CAD 快照校验、失效配置、错误响应和无效结果。另有 Windows 浏览器测试通过实际页面操作、CAD 生成、原版 EXE 和解析验证 DGB、ACB、N222；DGB 另验 Z 向载荷 2000 → 2400 N。原版文件和运行证据保存在本机。

在 `bearing-cad02` 环境下，向 Playwright 提供一个只包含这三组已审查配置的本机清单。需要同时验证原版二维出图时使用本地已授权的 CADImport bridge 和含 DWG/SQLite 的原版资源目录。

```powershell
$env:ROBAS_BROWSER_PROFILES = 'D:\local-robas-profiles\profiles.json'
$env:ROBAS_BROWSER_PORT = '8098'
$env:ROBAS_BROWSER_ARTIFACTS = 'build/solver06-browser-runs'
$env:PLAYWRIGHT_CHROMIUM_CHANNEL = 'chrome'
# 可选的二维出图实测
$env:ROBAS_WINDOWS_RESOURCES = '<已核实的原版 RoBAS 资源目录>'
$env:ROBAS_BROWSER_CADIMPORT = '<已授权的 CadImportBridge.exe>'
npx playwright test --config playwright.rolling.real.config.js
```
