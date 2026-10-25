# CAD-02 Day 3 — Web + OCCT 本地联动

本阶段新增浏览器页面里的 **精确 CAD（DRAFT）** 区域，提供油孔/环槽参数和即时生成按钮。与 CAD-01 原生预览分开：页面初始仍为 Three.js 纯参数示意网格；仅显式点击精确生成按钮后，才从 Python/CadQuery 后端加载生成的 STL 实体，查看可见油孔和环槽。

## 启动（Windows PowerShell）

请使用已经准备好 CadQuery 2.5.2、ezdxf、svgwrite 的 conda CAD 环境，且 Node.js 已安装。

```powershell
git pull origin main
npm ci
npm run build
conda activate bearing-cad02
python cad03_server.py --port 8088
```

**浏览器打开 http://127.0.0.1:8088/**，而不是 Vite 的 4173 端口。Day 3 后端同源提供静态 dist、生成接口和文件下载，运行在本地且不依赖外网。

基础流程：保持默认参数 → 点击「调用本地 OCCT 生成精确 CAD」→ 等待 STL 显示 → 隐藏轴及轴承座，观察轴瓦内槽 → 点击文件链接下载装配 STEP、单件 STEP、SVG/DXF → 修改轴颈参数，旧成果自动失效 → 再次生成。只勾选环槽不启用供油孔时会得到清晰错误提示。

运行 `npm run dev` 只提供 CAD-01 预览；不会启动 Python 精确建模服务。Day 3 需要 `npm run build` 和 `python cad03_server.py`。

## 测试

```powershell
node --test geometry.test.js cad03_geometry.test.js
python -m unittest discover -s tests -p test_cad03.py -v
python -m unittest discover -s tests -p test_cad02.py -v
```

`test_cad03.py` 真实生成一次三维模型并测试 API、阻止跨域、输入伪造确认、文件篡改等，耗时比无内核单测更长。

## 边界与限制

- 仅监听本机 `127.0.0.1`。不应在外网暴露本地 CAD 服务。
- 文件均为 DRAFT，未经轴承性能校核；无用户审批含义。
- STL 是 OCCT B-Rep 导出的显示网格，STEP 才是精确实体交换成果。
- 精确 STL 模式支持显隐、透明、爆炸和旋转；CAD-01 的三维扇形剖切只作用于示意模型。油槽可通过隐藏轴和轴承座观察，或在 FreeCAD 中剖切。
- 二维侧视/端视图来自实际 OCCT 正投影 HLR，并非完整标准制造图，也不是由实体剖切形成的剖视图。
- 本阶段未实现多 Agent/V3.1 状态集成，不允许网页或 Agent 伪造 confirmed 状态。
