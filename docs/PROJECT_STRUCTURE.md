# 项目结构

本仓库包含滚动轴承工作台和滑动轴承演示，两个工作台共享 Vite 构建配置。下面的目录均相对于仓库根目录，即包含 `package.json` 的目录。

```text
Bearing_CAD/
├── frontend/
│   ├── rolling/              滚动轴承前端、参数处理和二维工作台
│   └── sliding/              滑动轴承前端和三维查看器
├── bearing_cad/              滚动轴承 Python API、CadQuery/OCCT 建模及二维图纸流程
├── bridge/cadimport/         Windows CADImport 桥接源码
├── config/                   本机配置示例；真实配置由 Git 忽略
├── docs/                     文档索引、部署说明、设计记录和验收资料
│   ├── assets/               文档配图
│   ├── migration/            迁移过程与专题记录
│   ├── planning/             设计计划与任务书
│   └── v2/                   架构、几何规则、源码追溯和阶段验收
├── scripts/                  Windows 环境检查、桥接编译与启动脚本
├── tests-js/                 按 rolling/、sliding/ 分类的前端单元测试
├── tests/                    滑动轴承 Python 测试
├── tests_v2/                 滚动轴承 Python 测试
├── tests-browser/            两个工作台的浏览器测试
├── tests-browser-real/       浏览器、Python API 和真实 OCCT 联调测试
├── outputs/                  已纳入版本管理的滑动轴承示例输出
├── index.html                滑动轴承工作台入口
├── rolling.html              滚动轴承工作台入口
├── cad02_pipeline.py 等      滑动轴承 Python 模块及服务入口
├── package.json              Node 依赖和测试命令
├── environment-v2.yml        Python CAD 环境定义
└── vite.config.js            两个 HTML 入口的构建配置
```

## 找文件

- 修改滚动轴承网页：`rolling.html` 和 `frontend/rolling/`。
- 修改滚动轴承三维几何、API 或二维出图：`bearing_cad/`；CADImport 调用位于 `bridge/cadimport/`。
- 修改旧滑动轴承演示：`index.html`、`frontend/sliding/` 和根目录的滑动轴承 Python 模块。
- 环境和部署：`scripts/`、`config/`、[本机部署](robas-local-deployment.md)。
- 运行前端单元测试：`npm run test:unit:js`；两个工作台也可分别使用 `npm run test:unit:js:rolling` 和 `npm run test:unit:js:sliding`。

## 路径调整

原先根目录的 `rolling_*.js`、`rolling_workbench.css` 移到了 `frontend/rolling/`；滑动轴承的 `app.js`、`viewer.js`、`geometry.js`、`cad03.js`、`cad03_geometry.js` 移到了 `frontend/sliding/`。相应 JavaScript 测试移到了 `tests-js/`。根目录的 `WORKBENCH_README.md` 移到了 [sliding-workbench.md](sliding-workbench.md)，原 `docs/plannning/` 更正为 `docs/planning/`，`preview_2d.png` 移到了 `docs/assets/cad01-preview-2d.png`。旧迁移计划也已归档到 `docs/planning/`。历史阶段文档中出现的旧文件名反映当时的结构，请按此表查找当前位置。

两个 HTML 入口和滑动轴承 Python 脚本仍在根目录，现有访问 URL 和启动命令保持不变。`outputs/` 内的示例文件已受版本管理，不能简单当作缓存删除。

本机生成的 `build/`、`artifacts/`、`dist/`、`node_modules/`、`.pytest_cache/` 和 `test-results/` 不属于源码；Git 忽略这些目录。清理本机文件前应先确认其中没有需要保留的测试结果或 CAD 成果。

外部 RoBAS 资源和商业 CADImport DLL 使用本机路径，不存放在项目源码中。更多文档见 [文档索引](README.md)。
