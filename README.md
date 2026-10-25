# BearingCAD Studio — 圆柱径向滑动轴承二维/三维参数化展示样机

> 独立技术样机 / 不依赖 V3.1 LangGraph / **非工程发布图纸、未经承载和润滑校核**。

## 已完成的演示功能

1. 浏览器打开 `index.html`，录入轴颈直径 `d`、径向间隙 `c`、轴瓦外径、轴瓦长度、轴承座外径/长度。
2. 参数基本几何约束校验，自动计算轴瓦内孔 `d+2c` 和轴瓦壁厚。
3. 二维轴向剖视和端面视图同步更新；当前为示意，非符合 GB/ISO 工程图规范的图框/公差标注。
4. SVG、DXF、JSON 导出；其中浏览器导出的 DXF 采用简单线、圆、文本实体。
5. Three.js 三维交互预览（装配件/剖切/半透明/爆炸/旋转缩放），**需要浏览器能访问 jsDelivr CDN**；界面和 SVG/DXF 的生成可离线使用。
6. Python + CadQuery (OCCT) 生成精确 3D B-Rep 模型：STEP 装配和零件 STEP、STL，ezdxf 生成可被 CAD 读取的 DXF；输出存在 `outputs/`。

## 浏览器快速展示（无需运行 CAD 后端）

推荐在解压后的文件夹启动静态 HTTP 服务器（需要本机 Python；也可以使用 VS Code Live Server 等）：

```bash
python -m http.server 8080
```

浏览器打开 `http://localhost:8080/`（此处 localhost 是你自己的电脑）。直接双击 `index.html` 时部分浏览器会因 `file://` 模块安全策略阻止三维代码。**Three.js 动态加载在线依赖**，如果展示现场无网络，建议提前使用 npm/Vite 将 Three.js 固定版本打包为离线资源，或者准备 FreeCAD 等 CAD 查看器直接打开 `outputs/bearing_assembly.step`。SVG、DXF 不依赖三维库即可导出。

`outputs/bearing_assembly.step` 是**初始参数**导出的文件；网页修改参数时不会自动改变这个 STEP 文件。要得到新的 STEP，按下面步骤执行生成器。

## 重新生成精确 CAD 文件

安装 CadQuery 和 ezdxf（推荐用 Conda 创建独立环境；本项目当前已在含这两个库的环境实际运行）：

```bash
python generate_cad.py --params sample_params.json --out outputs
```

网页“下载 JSON”后，使用它作为 `--params` 输入，生成相应的 STEP、STL、SVG、DXF。输入 JSON 的 6 个字段如下：

```json
{
  "shaft_d_mm": 50,
  "radial_clearance_mm": 0.05,
  "bush_od_mm": 70,
  "length_mm": 50,
  "housing_od_mm": 86,
  "housing_length_mm": 60
}
```

*单位均为 mm。`radial_clearance_mm` 是单侧径向间隙，不是直径间隙。*

### 输出解释

| 输出 | 格式 | 用途 |
|---|---|---|
| `bearing_assembly.step` | STEP（OCCT B-Rep） | 精确 3D CAD 装配样例，3 个零件 |
| `housing.step`, `bushing.step`, `shaft.step` | STEP | 单件实体 |
| 同名 `.stl` | STL 三角网格 | 快速查看与几何验证，不含精确 B-Rep/单位元数据 |
| `bearing_section.dxf` | DXF | 二维剖视与端视线图（几何示意） |
| `bearing_section.svg` | SVG | 论文、答辩、演示使用的可缩放插图 |
| `design_snapshot.json` | JSON | 可追溯参数快照；明确标记 `DEMO_UNVERIFIED` |
| `artifact_manifest.json` | JSON | 记录参数 SHA-256、各成果 SHA-256、生成器版本及 DRAFT 状态 |

## 设计约束与局限

- 仅套筒轴瓦、轴和轴承座的基本同轴几何，尚无油孔/环形油槽/轴向油槽、止推结构、倒角、分体轴瓦、制造公差等。
- 轴瓦内孔 `d+2c`，轴和孔的径向间隙按照真实大小建模，不刻意夸大。缩略图中几乎看不到间隙是正常现象。
- 现阶段二维图与 3D 采用**相同参数独立构造**，不是由三维 CAD 自动投影得到的完整工程图；不可称为“自动出正式国标工程图”。
- 三维剖切展示只是浏览器中的显示几何变化，不改变 Python 输出的完整实体；工程化后应使用 OCCT 几何剖切和可追溯投影生成。
- 浏览器中的参数状态只是本地草稿，**不能直接视作用户在 V3.1 系统内的确认**。
- 没有集成性能计算，也没有适用性审核，不能以此判断轴承可制造、可承载或满足标准。

## 针对 V3.1 的正确接入方式

设计系统（LangGraph / 后端）只向 CAD 服务提供经过 schema 校验的不可变 `DesignGeometrySnapshot`：

- `bearing_type`: `plain_journal_cylindrical`
- `candidate_id`, `candidate_version`, `geometry_revision`
- `geometry` 上述 6 项，单位 mm
- `approval_state`: `DRAFT|CONFIRMED`，由后端状态管理系统生成，不信任 Agent 输出
- `geometry_hash`: 对单位规范化后的 geometry 做稳定序列化生成 SHA256

CAD 模块只读参数和 `approval_state`，不得替 Agent/用户更新确认状态。草案支持预览和带水印草稿导出；正式输出需后端检查用户确认和快照 hash 与最新方案一致。

详细拆分见 `IMPLEMENTATION_PLAN.md`。

## 原版 RoBAS 源码对照

师兄软件三维：Eyeshot 12 的 Solid 创建、布尔差、装配、渲染。二维：DWG 模板加载，替换 CADText 并转为 DXF。独立新实现避免依赖其 WinForms、.NET 4.5.2、Eyeshot 商业 DLL、缺失 DWG 模板及相对路径 NetLib 子工程。原项目源码与逻辑的复用也需确认授权。
