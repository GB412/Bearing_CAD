# 3D-MIG-09C：独立三维 CAD 功能级交付候选

## 范围冻结
- 只支持深沟球、圆柱滚子 N/NU/NJ/NF/NUP、角接触球；详细保持架按现有 `bearing-cad.request.v1` 参数输入。
- Windows 本地 loopback API + Vite 打包 Three.js 三维查看，导出可下载真实 B-Rep 生成的 STEP/STL。
- 原滑动轴承 CAD-01 入口不删除不重写。
- **明确不包含多 Agent 适配/确认逻辑、不新增滚动轴承二维工程图、不声称厂家制造认证。**

## 交付清单

| 项目 | 自动验收证据 | 交付结果 |
| --- | --- | --- |
| 三类轴承及详细保持架真实 STEP | 七组 07A 真实 OCCT 基准与所有 V2 回归 | 代码与测试已实现 |
| 网页直接调用真实 CAD API，非模拟模型 | 09A 新 rolling-real-e2e 作业 | 以 PR09A 全绿为准 |
| STEP 回读与几何质量 | `geometry_quality.json` + 缓存 SHA-256 | 09A/08A 门禁 |
| 一台新电脑可以按 README 启动 | Conda 固定环境、Node lockfile、Windows 步骤 | 文档已准备，跨机器人工验收待办 |
| FreeCAD 独立打开 STEP 与目视 | `3d-mig-09b-freecad.md` + `freecad_import_review.json` + 截图 | **人工验收 PENDING，不能假定通过** |
| 与 RoBAS Eyeshot STEP 逐点实体对照 | 需要同参数旧版模型 | **NOT_AVAILABLE / UNVERIFIED** |
| 多 Agent 集成 | 不在范围内 | 已暂停 |

## 演示流程（约 8 分钟，演示节奏不是异步执行承诺）

1. 从已激活的 `bearing-cad-v2` 环境启动 `python -m bearing_cad.api --port 8090 --static dist`。
2. 打开 `http://127.0.0.1:8090/rolling.html`；深沟球选择双半笼铆接保持架，确认 26 个独立实例、切剖/透明、零件树和下载。
3. 切到圆柱滚子 NUP 勾选圆柱窗孔保持架，确认 15 个实例及独立活动挡圈。
4. 切到角接触球 25° 勾选径向窗孔保持架，确认 14 个实例。
5. 下载 `bearing_assembly.step` 与 `geometry_quality.json`，说明几何检查范围、缓存哈希以及“非制造批准”限制。
6. 展示已在另一应用核查过的 FreeCAD 文件（**若未完成，不得谎称已审查**）。

## 失败处理与发布判定

- 后端不可用：检查当前 Conda 环境、8090 端口、`npm run build` 的产物和浏览器地址是否为本地同源。
- 参数错误：按照 API 的 422/field_path 修正，旧模型清空是预期安全行为。
- STL 和 STEP 不一致：停止发布，保留输入/manifest/质量报告，创建单独修复 PR。
- FreeCAD 无法打开/实例数量不对：不允许记录为完整验收通过；记录案例、软件版本与步骤。
- **本交付的级别为功能级独立三维 CAD 演示候选。** 若 09B 人工实际检查未完成，不能把整个项目写成制造级验收完成。

## 已冻结后续边界
`PR10 / 多 Agent 集成` 不纳入本阶段任何 PR；什么时候开始需要用户另行决定。正式滚动轴承 2D 制图也不纳入。
