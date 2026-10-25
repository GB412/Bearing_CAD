# 旧 Bearing_CAD 项目审查与复用建议

范围：`BearingCAD_Demo/` 当前滑动轴承 demo，检查参数、OCCT 后端、导出、二维、Three.js、HTTP、缓存/manifest 与测试。该仓库现状可用于提取经过测试的技术做法，但不作为 CAD-V2 的架构基础。

## 1. 分类结论

| 子系统 | 旧实现与可复用资产 | 主要局限/风险 | V2 处理建议 |
|---|---|---|---|
| 参数模型/验证 | `cad02_pipeline.py:26–95` 的冻结 dataclass、规范化、输入解析和后端重新校验；`geometry.js:1–16` 的前端范围提示；无效参数会阻断导出 | 仅有 journal bearing 字段；前端 `geometry.js` 和后端 Python 两套验证规则，存在重复维护；尺寸边界是 demo 限制，不是工程规范 | 复用“不可变请求、规范化输入、后端为权威验证”的思想；重新定义轴承类型 discriminated schema、单位、角度、构型、版本、错误路径；UI 校验只作即时提示 |
| 3D CadQuery/OCCT | `cad02_pipeline.py:99–150` 建模后检查单实体、体积、有效性和 B-Rep；滑动轴承示例表现了 CadQuery 生成精确实体的路线 | 只支持 housing/bushing/shaft，模型和特征字段具体绑定滑动轴承；B-Rep 检查只覆盖当前部件，没有通用组件/装配合同 | 可复用 Python/CadQuery/OCP 依赖路线和 topology checks 的概念；V2 重写为独立几何构造器、组件协议和轴承 builder，不扩展旧模型分支 |
| STEP/STL | `cad02_pipeline.py:278–288` 零件/装配 STEP、STL；STEP 是装配，STL 参数控制精度 | 文件命名和零件种类写死；STL 和 STEP 导出行为耦合在一个 pipeline；未形成跨轴承的坐标/实例契约 | 抽象 ExportService/ExportProfile：B-Rep 是真源，STEP 装配保留组件/实例名，STL 分件供预览；导出后抽查/测试 STEP 回读和 hash |
| 二维 DXF/SVG | `cad_workbench_drawing.py:17–36` 通过 OCCT 半空间求交生成真实剖面实体；第 40–56 行有名义装配碰撞检查；第 104 行起同源 HLR 端面投影、剖面线和图纸；`cad02_pipeline.py:157–240` HLR 投影 | 图纸版式、三零件名称、尺寸标注直接绑定 journal bearing；等轴视图/尺寸公式没有 drawing view abstraction；图纸标注不含滚道/滚子/保持架；明确不是制造图 | 可复用“从 B-Rep 截面/HLR 产生几何线稿而非手绘形状”和 DXF audit 思路；新建 drawing scene/projection/dimension/title block 分层，定义图纸状态与标准能力边界 |
| 浏览器 Three.js | `viewer.js:1–20` 本地依赖离线渲染；第 21–48 行异步加载精确 STL；失效清空和 load serial；可见/透明/爆炸；Playwright 覆盖基本交互 | 参数化示意网格和 OCCT STL 两种模式同时存在；默认对象和 exact objects 都是三个固定数组；explode、显示控件、配色和检查 snapshot 靠数组顺序；模型坐标/单位假设和相机范围固定 | 可复用 STLLoader、OrbitControls、资源释放、失效竞争防护；Viewer 改为读取 manifest 的 part/instance/transform/material/category/view metadata，组件清单动态化 |
| HTTP | `cad03_server.py:15–71` loopback server、same-origin 检查、Content-Length 上限、请求校验、缓存文件路由、路径防穿越 | 单进程同步生成；端点和字段仅一个滑动轴承版本；Host/Origin 设计为本地 demo；通用错误隐藏实际细节；无 job id、取消、并发去重、队列和能力清单 | 仅复用开发阶段 loopback/请求大小/来源限制的防护点；引擎核心不绑定 HTTP；先做 service API，再由 adapter 暴露版本化接口，错误使用稳定 code + field path + diagnostic id |
| 缓存/哈希/manifest | `Design.geometry_hash` 和 `cad02_pipeline.py:242–317` 文件 hash 校验、generator version key、原子 staging directory、产物 manifest；服务读取时再次校验 | key/version 界定和 cache path 是本项目格式；manifest 文件 schema 缺少统一类型/实例/坐标/校验字段；缓存目录并非跨平台 job store；hash 是几何请求/参数的标识，不等于审核批准 | 复用 canonical serialization、输入 hash + generator version、逐文件 SHA256、生成临时目录再原子发布；新 schema 版本化，hash 含 bearing type、规范化参数、规则版本、CAD engine/OCCT 版本、导出配置 |
| 测试 | `tests/test_cad.py` 参数负例；`test_cad02.py` 参数 hash、拓扑/体积、特征、投影和 tamper；`test_workbench.py` 剖切与图纸包；`test_cad03.py` API 安全/缓存；Playwright 覆盖 UI | CAD 内核和 ezdxf 在当前环境未装：真实几何测试失败而非 skipped（部分旧测试把可选依赖缺失显式跳过）；统一测试入口当前 7 errors/1 fail/2 skips。缺失内核导致 Web generate 500 | 复用测试分层和负例思路；V2 CI 必须 pin CadQuery/OCP 并强制几何测试，不允许对真实 CAD 用例静默 skip；将参数/公式测试、拓扑测试、STEP roundtrip、API、浏览器按层分开 |

## 2. 已识别的架构性耦合

1. `Design`、`build_models`、`validate_models`、导出、投影、缓存、manifest、generation 全在 `cad02_pipeline.py` 单文件中，feature 字段也用滑动轴承命名，混合领域模型与基础设施。
2. 旧 demo 提供两种 CAD 真值来源：`viewer.js:72–89` 的 Three.js 近似参数化网格，以及后端 CadQuery B-Rep 导出的精确 STL；两者视觉可能相似但几何地位不同。新引擎只将 OCCT B-Rep 作为 CAD 真源，Web mesh 是派生预览数据。
3. `app.js:7–32` 手工拼 SVG 草图、`geometry.js:17–32` 另行拼 DXF；CAD-02 drawing module 又用真实 OCCT HLR 和剖面生成 review DXF/SVG。它们不应继续并存为同一“正式图纸”出口。
4. 服务允许的 FILES 集合、前端下载链接和 viewer 加载的三件零件名都各自硬编码（`cad03_server.py:11`、`cad03.js:43–46`、`viewer.js:36–38,50`），随滚动体数量/类型扩展会产生并行改动漏项。
5. 现有结构图和 STEP 的 `approval_state=DRAFT`、提示语是好的状态意识，但“参数/文件哈希一致”只证明产物对应输入，不证明轴承经过工程审核。

## 3. 推荐保留的“做法”，不保留旧边界

- 以明确单位字段、不可变请求和服务端校验为基础。
- 使用 OCCT B-Rep 真源，导出中性 STEP 及容差可记录的 STL。
- 生成后验证每个 solid 的有效性、体积、包围盒、装配碰撞/间隙，错误时不发布半成品。
- 图纸使用 OCCT 投影/剖切来保证与三维几何同源。
- canonical parameter hash、生成器版本、逐文件 SHA256、原子目录发布与 tamper 校验。
- loopback 开发接口的请求限制、same-origin 检查和浏览器过期异步请求清除。
- 分层自动测试，特别是负例、导出/回读、API 和生产浏览器端到端用例。

旧项目中的固定模型、滑动轴承约束、路线/文件名、三零件清单、旧 HTTP path、图纸版式和参数范围都留在旧项目，不纳入 `bearing_cad` 核心依赖。
