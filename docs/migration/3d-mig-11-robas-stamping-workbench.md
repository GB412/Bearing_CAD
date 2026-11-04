# PR-04 · RoBAS StampingCage 预填接入 CAD 工作台

## 实现范围

- 保持 PR-03 的 `robas_stamping_profile` 独立源码实现；此 PR 仅增加本地 HTTP 和用户可选预填按钮。
- HTTP: `POST /api/v2/cad/sizing/dgb-stamping`，仅允许回环地址和同源请求，严格校验必填字段；所有尺寸保持 mm。
- 不要求 RoBAS 原版 CSV、DWG、CADImport DLL 或外部 EXE：该冲压候选预填只使用 C# 中确定的计算公式。
- UI: 只有选择“深沟球轴承 → 包含保持架 → 双半笼 + 球兜 + 铆钉”时才显示该按钮；按下后计算并填充**现有显式请求字段**。
- 型号采用新的“RoBAS 保持架计算型号”输入，默认 6008，与二维图纸的单独型号输入互不修改。原版仅使用型号的 60/62/63 系列前缀计算板厚和宽度。
- 用户输入的 `rivet_hole_clearance_mm` 作为**显式 CAD 孔净距**传入适配器；不把它误认为师兄的制造公差。
- 返回结果被标记为候选，先检查字段和几何外形条件，再一次性写入 UI；人工修改参数时旧异步请求不能覆盖新数据。

## 原版 Width 与 CAD width_mm

原版 `StampingCage.Width = Kc * ballDia`，`InsideDiameter = pitchDia - Width`，`OutsideDiameter = pitchDia + Width`。该 Width 对应**环带径向厚度**（而非轴向总宽）；现有 CAD 的 `cage.width_mm` 是总轴向包络：

`axial_total = 2 * (0.55 * ball_d_mm + board_thickness_mm)`

原版板厚、球兜半径、孔径和球头直径仍取 `StampingCage.cs` 原始分支表。该适配继续使用当前 OCCT 双半笼实体构造器；尚缺相同参数下的原版 Eyeshot STEP 验证。

## 明确边界

- 型号仅用于选择原版冲压设计公式系列。**未验证型号与当前内径/外径/宽度符合标准型号目录**；生成前需人工确认。
- 原版构造函数不提供新的孔净距，也不提供独立制造工艺验收结论。
- 不调整原版 DWG/CADImport 二维绘图桥接器，不增加未核实制造公差；现有 2D 图纸沿用显式 CAD 设计参数推导的已确认尺寸。
- 不实现 DGBOptimizer、载荷分析或求解 EXE；所有生成结果仍非制造批准。

## 测试

- Python HTTP：无原版资源时可调用；来源参数、状态码、额外字段、错误型号和跨域拒绝。
- Playwright：选择保持架后显示按钮、参数填充、二维型号不变、切换类型隐藏按钮、过期计算结果不覆盖用户输入。
- 现有完整 OCCT STEP/STL、二维/三维浏览器端到端回归仍为合并门禁。
