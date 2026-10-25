# BearingCAD Studio: CAD-01 Demo

这是一个滑动轴承二维/三维参数化设计展示样机。页面明确标记为 `DEMO / 未经工程校核 / 非正式制造工程图`，不代表已审核的制造图纸，也不接入 V3.1 多 Agent 状态体系。

## 前端启动

需要 Node.js 20 或更高版本。首次安装和启动：

```powershell
npm ci
npm run dev
```

打开 Vite 输出的本地地址（默认 `http://127.0.0.1:4173`）。现场离线演示前，在有网络的机器执行 `npm ci` 和 `npm run build`，然后把整个项目目录（包括 `dist/`）带到演示电脑。生产构建可用以下命令预览：

```powershell
npm run preview
```

Three.js `0.180.0` 和 Vite `7.1.7` 已写入 `package-lock.json`，由 Vite 打包到本地资源；运行时不依赖 CDN 或外网。不要双击 `index.html`，使用 Vite 服务器以保证 ES module 和 STEP 静态资源按 HTTP 方式加载。

## CAD-01 功能

- 轴、轴瓦、轴承座三件装配的 Three.js 预览，支持旋转、缩放、单件显隐、剖切、半透明和轴向爆炸。
- 参数修改后，二维轴向剖视、端面视图、标注和三维模型使用同一组 mm 参数即时更新。
- 合法参数可下载 SVG、浏览器生成的 ASCII DXF 和参数 JSON；非法参数会清空预览并禁用导出。
- 页面提供 `outputs/bearing_assembly.step` 下载。它是仓库内固定演示参数（`sample_params.json`）生成的样例，修改页面参数不会自动改变该文件；新的 STEP 需要运行 Python 生成器。

浏览器 DXF 是 CAD-01 的示意线稿出口：使用 AC1015、`$INSUNITS=4`（毫米）、明确的 `HOUSING/BUSHING/SHAFT/CENTER/DIM/TEXT` 图层，并在文本中保留关键尺寸和 Demo 水印。它已做结构和尺寸自检，但没有在本环境宣称通过 QCAD/FreeCAD 的正式互操作验收。

## 测试

```powershell
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:browser
```

浏览器测试使用 Chromium 离线模式，覆盖页面加载、三维 canvas、代表性参数同步、非法参数清空和导出阻断、视图控制，以及生产服务器提供的固定 STEP 文件。GitHub Actions 在前端构建和不依赖 CadQuery 的 Python 测试上执行同样的门禁。

## 精确 CAD 后端（可选）

CadQuery/OCCT 生成器属于本阶段已有的独立 Python 出口，不是浏览器动态 B-Rep。建议使用 Conda 安装与项目匹配的 CadQuery 环境，再安装 `requirements-cad.txt` 中的 `ezdxf` 和 `svgwrite`：

```powershell
python generate_cad.py --params sample_params.json --out outputs
```

它生成 STEP、STL、服务器端 DXF/SVG、参数快照和 manifest。CadQuery 未安装时，基础 Python 测试仍可运行，实体体积测试会明确显示为 skipped；不会把缺少 CAD 内核误报成通过。

## 验收边界

本仓库只实施 CAD-01。二维图是参数化结构示意，三维剖切是浏览器显示效果，不能称为正式 GB/ISO 制造工程图。油孔、油槽、公差、承载/温升计算、权威 B-Rep 投影、候选确认和 V3.1 集成属于后续范围。
