# CAD-V2-00 验收报告

日期：2026-10-26。范围：RoBAS 几何源码审查、旧 Bearing_CAD 评估、统一 CAD 引擎架构决策。未实现任何滚动轴承模型或业务代码；未改写/复制 RoBAS 源文件。

## 1. 交付文件

- `docs/v2/source_traceability.md`：RoBAS 三类轴承从 `Plot3DModel()` 到圈/滚动体/保持架构造的调用链与依赖。
- `docs/v2/geometry_rules_register.md`：几何参数、单位、公式、来源缺口与风险登记表。
- `docs/v2/legacy_assessment.md`：旧滑动 CAD 的可复用做法、硬编码与重构边界。
- `docs/v2/architecture_decisions.md`：独立 `bearing_cad/` 包结构、契约、依赖方向、数据流、错误/任务/缓存和 PR-01 边界。
- `docs/v2/CAD-V2-00-acceptance.md`：本验收记录。

## 2. 主要源码审查结论

1. RoBAS 是 Eyeshot/WinForms 场景里的绘制模型，不是与 UI 解耦的 CAD 引擎；绘图路径用 Eyeshot `Solid` 做圆柱、环面/滚动体布尔并写入 Model。可迁移的是经核证的几何关系和构型意图，不能把 `Plot3DModel` 当可移植的导出层。
2. 三类轴承有明确组件组织：深沟球=内外圈+球阵列+冲压/简化保持架；圆柱滚子=内外圈挡边构型+滚子阵列+笼；角接触球=角度相关沟道+球阵列+直兜保持架。构型差异要作为 schema 中显式字段。
3. 多个几何参数重载、默认值和 Plot3D 重新构造路径不一致。迁移前必须以源码行/方法为单位完成公式、单位和实际调用分支追踪。
4. 旧 CAD 有 CadQuery/OCCT、真实 B-Rep 半剖和 HLR 图纸、哈希 manifest、tamper 检测、离线 Three.js 与较好的浏览器行为测试，适合复用工程做法；其 domain contract、三件零件命名、图纸/界面和后端 pipeline 绑定滑动轴承，不作为 V2 基础。

## 3. 风险摘要

- RoBAS 几何内部主要用米、展示属性多转换为毫米；有不同构造器使用不同缩放因子的情况。
- 深沟球 `Dpw=(D+d)/2` 与另一构造 `Dpw=(d+d)/2` 不一致；滚动体数量公式中的 186 度常数来源未记录。
- 角接触 ACBGeometry 默认 25 度输入直接用于 `Math.Sin/Cos`，而 Plot3D 传给 race constructor 时显式转弧度，存在高风险角度单位歧义。
- 球/滚子、race groove、挡边以及笼尺寸由多条重复/缺来源公式产生；相切、碰撞、壁厚、布尔有效性没有贯穿 Plot3D 的系统报告。
- SpherePocketCage 和 StraightPocketCage 先切一次兜孔再执行 `i<=pocketNum`，存在首孔重复及多一次 Boolean 的风险。
- 圆柱滚子 NUP 在 Plot3D 映射为内外圈双挡边，没有显示独立挡圈组件，构型可能被简化表达。
- RoBAS 源代码/Eyeshot 使用及分发授权尚未确认；不得假设可复制进正式包或公开仓库。

## 4. 测试执行结果

执行于 `D:\RotorStudio\BearingCAD_Demo`：

| 命令 | 结果 |
|---|---|
| `npm run build` | 通过。Vite 生产构建成功；有主 JS bundle 超过 500 kB 的性能提示。 |
| `npm run test:unit:js` | 通过：4 passed，0 failed，0 skipped。 |
| `npm run test:browser` | 通过：Playwright 4 passed，覆盖离线生产页面、非法输入清空、视图交互和固定演示 STEP/DXF。 |
| `python -m unittest discover -s tests -v` | 未通过：19 tests，1 failure、7 errors、2 skipped。纯参数/拒绝请求/API 状态用例通过；涉及 CAD 几何的多个测试因 `cadquery` 未安装而 error；图纸 DXF 测试因 `ezdxf` 未安装而 error；CAD-03 generate 返回 HTTP 500。两个旧 CAD-01 可选依赖测试明确 skip。 |
| `npm test` | 同一 Python unittest suite，结果相同：19 tests，1 failure、7 errors、2 skipped。 |

Python 错误共同环境原因：当前解释器缺少 `cadquery`/OCP 和 `ezdxf`，而部分 CAD-02/Workbench/API 测试直接执行精确 CAD 并失败。服务端把此处异常映射为通用 500。未安装额外依赖或修改测试结果。

## 5. 验收状态与 CAD-V2-01 条件

**文档审查交付完成；不满足直接进入第一个真实滚动轴承几何实现 PR 的条件。**原因是：真实 CAD 依赖环境未就绪、旧 CAD 的真实几何测试未能通过、RoBAS 公式存在需裁决的单位/调用链疑点、源代码许可与改作授权未确认、主系统 adapter 契约仍待定义。

可进入“引擎基础契约与质量门禁”型 CAD-V2-01（不建轴承模型）的前置事项：

1. 由项目负责人确认 `.reference/RoBAS` 源码的阅读、改写和目标交付范围授权；只保存自有代码与可核证的公式说明。
2. 为目标仓库建立可复现并 pin 的 Python/CadQuery/OCP/ezdxf 环境和 CI；在该环境重跑当前 CAD 几何与导出测试，记录实际 pass/fail，不将缺依赖视为通过。
3. 确认 V2 新包落点、最低 Python/OS 目标、请求方字段和多 Agent adapter 生命周期/状态边界。
4. 将 ACB 角单位、DGB 节圆公式、Z 算法和笼孔重复切除列为审计问题；真实模型阶段前需有公式决策记录和几何基准 fixtures。

CAD-V2-01 若严格限于契约/注册/缓存探针和内核环境门禁，可以在上述事项落实后开始；三类真实滚动轴承模型仍应由后续独立 PR 实施。

## 6. 未覆盖项

- 本次未用 Eyeshot 构建/运行 RoBAS，未对其 Solid 布尔进行实体验证或许可证法律审查。
- 未在 FreeCAD/QCAD 中对旧 CAD 生成文件做人工互操作检查；当前环境缺少 CadQuery/ezdxf，因此也未新生成精确实体。
- 未连接多 Agent 主系统验证其设计参数 DTO、同步/异步调用、artifact 存储和候选审批状态机。
- 所有工程载荷能力、寿命、材料、公差、润滑、制造和标准符合性均不属于本次验收范围。
