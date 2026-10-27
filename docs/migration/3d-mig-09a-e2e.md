# 3D-MIG-09A · 浏览器到真实 OCCT/STEP 端到端验收

本 PR 的核心要求是 **不 mock API 或 STL 文件**，而是让 Playwright 从与生产演示相同的 loopback 服务中访问已构建的 Vite 工作台，发起真实 JSON 请求，由 CadQuery/OCCT 生成实际 STEP/STL 和 SHA 清单。

## 本地运行

在已安装 Node 依赖、Playwright Chromium 和 `environment-v2.yml` 的 CadQuery Python 环境后：

```bash
npm ci
npm run build
npx playwright install chromium
npx playwright test --config playwright.rolling.real.config.js
```

测试配置会自动启动 `python -m bearing_cad.api --port 8090 --static dist --artifacts build/real-browser-e2e-artifacts`。服务仍限制在 127.0.0.1，不引入远程部署或认证功能。

## 场景与严格门槛

单次真实浏览器会话依次验证：
1. 深沟球 `stamping_double_half`：**26 实例 / 6 原型**，每片半笼与 11 枚铆钉为独立实例。
2. 圆柱 NUP `cylindrical_window`：**15 实例 / 5 原型**，独立可分离活动挡圈。
3. 角接触球 25° `straight_pocket`：**14 实例 / 4 原型**。
4. 每一步浏览器显示 STL 三角面数>0、manifest 实例/原型数匹配；从真实 HTTP 下载 `bearing_assembly.step`，核对 STEP 文件头与非空文件，并下载 `geometry_quality.json` 检查实例数、STEP 回读和质心对照。
5. 真实非法参数 HTTP 422 后，旧模型、零件树和成果下载必须清空，页面应明确报错。
6. GitHub 新 `rolling-real-e2e` job，固定 Micromamba CadQuery + Node22 + Chromium。在 CI 上完整运行真实后端。

## 边界

这是一份**真实工作台→真实 Python HTTP→OCCT B-Rep→STEP/STL→浏览器**的自动化 E2E 证据，不是 FreeCAD 或其他独立内核的人工打开验收，也不证明原版 RoBAS Eyeshot 逐点等价。09B 需单独评审。测试重型运行不替换原本较快的模拟浏览器回归测试。
