# 向 Codex 交付的 CAD 模块实施与验收计划（建议拆为 3 个独立 PR）

## 本周目标（演示优先）

现场演示 2~3 分钟：打开页面 → 修改轴颈直径 50→60 mm（同时将轴瓦外径 70→82、座外径 86→100，保持结构有效）→ 二维和三维同步变化 → 剖切与轴向爆炸 → SVG、DXF 下载 → 用 FreeCAD 等 CAD 查看器打开预生成的 STEP → 回到设计方案展示参数来源。不能把示意图说成制造图。

### PR CAD-01 — 可独立运行的同步参数样机

- [ ] 建立前端单独 package，固定 Three.js 的版本并让依赖离线打包（不要生产依赖 CDN）。
- [ ] 参数 schema：统一 mm；专门字段 `radial_clearance_mm`，绝不混用半径/直径间隙。
- [ ] 实现圆柱径向滑动轴承 3 件套：轴、轴瓦、轴承座；剖切、爆炸、透明、旋转缩放。
- [ ] SVG 轴向剖视和端面视图，支持直径/宽度/间隙数值；导出 DXF/SVG。
- [ ] 同一组参数导出的几何和图纸尺寸必须一致，不合格输入明确阻断。
- [ ] 10 组边界和非法输入用例；视觉对照至少 3 组参数。
- [ ] 不接入 V3.1 Agent 状态，不修改设计参数来源、用户确认和候选管理逻辑。

**验收**：断网浏览器可旋转模型（需离线打包）；参数变化后画面/尺寸即时更新；DXF 在 QCAD/FreeCAD 打开且几何单位是 mm。暴露 Demo 水印。

### PR CAD-02 — 精确 B-Rep CAD 和文件出口

- [ ] 选择后端 CadQuery/Python + OCCT（推荐契合 Python V3.1）或纯浏览器 OpenCascade.js；二者择一作为权威建模引擎，避免长期重复几何内核。
- [ ] 3D B-Rep 导出 STEP（装配与单件）、STL（三角网格）。导出任务幂等：键由 `geometry_hash + format + generator_version` 构成。
- [ ] 几何有效性检查：非空实体、零件数、体积、封闭性、孔径 > 轴径、轴向对齐。
- [ ] 给完整实体加入可配置的油孔和油槽，但设计参数必须先有权威规则，不能让 LLM 构造拓扑实体。
- [ ] 使用真实几何投影生成二维剖视/投影基础线稿；再添加尺寸和标注。
- [ ] 记录几何版本、生成内核版本、源参数哈希、文件哈希。

**验收**：3 种尺寸和至少 1 种结构配置的装配 STEP 可被第三方 CAD 打开；重新导出不产生多份互不一致版本，图纸与实体关键尺寸偏差在预设公差内。

### PR CAD-03 — 集成 V3.1 状态体系与工程图升级

- [ ] 从已有 V3.1 后端只读获取 immutable geometry snapshot；严禁通过 Agent 自行标记 CONFIRMED。
- [ ] 允许 `DRAFT` 预览；只有 V3.1 状态管理器允许确认后，才可以执行正式发布接口。
- [ ] 实现 `CADGenerateRequest`、`CADArtifactManifest`；附 `candidate_id/version`、`geometry_hash`、`approval_state`、产物 hash。
- [ ] 增加审批后参数更改的旧导出失效检查；候选之间隔离缓存。
- [ ] 实现 ISO/GB 工程图规范所需的主视/剖视、隐藏线、中心线、尺寸/公差、粗糙度、技术要求、明细栏与图签模板（由轴承专业老师复核）。
- [ ] 前端从真实候选设计方案读取，用户拒绝草案不得落为最终成果。

**验收**：未确认候选只能导出带 DRAFT 标识的预览；已确认候选可生成经完整性校验的正式文件；同名但不同哈希的几何不复用错误文件；参数改变后必须重新生成 CAD 文件。

## 接口建议

```json
{
  "candidate_id": "candidate-001",
  "candidate_version": 3,
  "bearing_type": "plain_journal_cylindrical",
  "geometry_unit": "mm",
  "geometry_revision": 1,
  "geometry": {
    "shaft_d_mm": 50,
    "radial_clearance_mm": 0.05,
    "bush_od_mm": 70,
    "length_mm": 50,
    "housing_od_mm": 86,
    "housing_length_mm": 60
  },
  "approval_state": "DRAFT",
  "geometry_hash": "SHA256-computed-server-side"
}
```

`approval_state` 和 `geometry_hash` 由可信后端产生，不允许前端或 Agent 自报；示例字段仅演示传输结构。上面的轴承几何数值不是可靠设计推荐。

## 架构取舍

- Three.js 只负责显示 Mesh 与交互，不承担精确 B-Rep 或 STEP 生成。
- CAD 内核只负责确定性几何，LLM 仅为参数和诊断提供人机解释，不直接生成关键几何代码。
- SVG 用于交互式预览；DXF 用于二维矢量编辑；STEP 用于可交换的实体 CAD；STL 用于网格查看/制造数据交换。不要把 STL 当作 STEP。
- 先不把 WinForms/Eyeshot 迁成服务，也不复制源项目原有 CAD 模板（当前压缩包缺失模板），避免与本周展示目标冲突。
- OpenCascade.js 适用于浏览器内核；若使用 replicad，先做 AGPL 许可证适配评估；若使用 Python CadQuery 可减少与 V3.1 Python 代码的集成复杂度。
