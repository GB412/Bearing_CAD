# CAD-V2-07 审查与验收

## 前置代码审查
- 基线：`main@f0d88f6e006ea43f44369a3ecf3f5e29ab82e374`；CAD-V2-01～06 已合并。
- 新 API 只接受同源 Origin，先前并未托管页面；因此 V2 页面需从同一个 Python loopback API 服务提供，而非让独立 Vite 端口跨域调用。
- V2 成果采用原型 STL + 装配实例。11 颗钢球共享一个球体 STL，通过 11 个不同实例平移装配。新 UI 必须据 manifest 展开实例，不能用 Three.js 临时计算轴承替代精确 CAD。
- 原有 `viewer.js` 为滑动轴承三个特定零件硬编码；本 PR 不改变旧工作台业务行为。
- 目前 manifest 只提供 translation（无任意旋转）。深沟球球形滚动体可被正确显示；将来迁移非轴对称滚子或姿态变换时应扩展 manifest 和 Web renderer，不自行猜姿态。

## 开发内容
- 独立 `rolling.html` / `rolling_workbench.js` / `rolling_workbench.css`：深沟球参数、可选简化保持架、真实 STL 装配实例、零件树、显隐、爆炸、透明、可视裁切、视角复位、下载与质量状态。
- `rolling_manifest.js`：参数和文件 URL 白名单、部件定义与实例严格检查；异步加载场景下防旧请求覆盖新模型。
- `bearing_cad/api.py` 增加可选 `static_root` 和 `--static dist`，限定 `rolling.html` 与 hashed js/css assets，同源调用现有 CAD API；不会公开原滑动轴承页面。
- Vite 多入口不改变 `index.html` 和既有演示 STEP 打包，CI 新增 Node 合同测试和双页面构建。
- 新增 `tests_v2/test_workbench_static.py` 验证静态路径白名单，`rolling_manifest.test.js` 验证实例和 URL。

## 执行
```powershell
npm ci
npm run build
python -m bearing_cad.api --port 8090 --static dist --artifacts artifacts/cad-v2
```
打开 `http://127.0.0.1:8090/rolling.html`。

## 限制与门禁
- “半剖”只裁切浏览器网格，不产生新的 STEP 剖面或工程图；无承载能力/寿命/公差/制造级校验；保持架为简化概念模型。
- 必须通过 GitHub CAD-V2、CAD-01/02/03、Workbench 旧回归、Node 合同和 Vite build。
- 浏览器端应进行真实有/无保持架测试和界面交互核验；如果没有执行 Playwright/独立浏览器，就如实记录为“未验证”，不可宣称视觉效果已验收。
