# CAD-02 精确 B-Rep 与工程线图（开发中）

CAD-02 是独立的确定性 Python/CadQuery/OCCT 生成器。原来的 CAD-01 浏览器演示和 generate_cad.py 仍保留，不改动多 Agent/V3.1 用户确认机制。**当前输出均为 DRAFT 演示成果，不是通过专业审核的制造图。**

## 环境与运行

建议使用 Python 3.11、CadQuery 2.5.2（含 OCP）及 requirements-cad.txt 中的 ezdxf、svgwrite。完整 OCCT 环境中执行：

\`\`\`bash
python cad02_pipeline.py --params sample_params_cad02.json --out artifacts/cad02
python -m unittest discover -s tests -p test_cad02.py -v
\`\`\`

原有六项必填字段保持兼容。可选新增：
- \`oil_feed_hole_d_mm\`：在 +X 方向贯穿座体和轴瓦的单个径向供油孔；
- \`annular_groove_width_mm\`：轴瓦内孔中央环形油槽的轴向宽度；
- \`annular_groove_depth_mm\`：槽底相对原内孔的径向深度。

槽宽和槽深必须成对提供，本演示要求同时具有供油孔。所有值单位毫米，数值精度 0.001 mm。限制来自**几何拓扑可用性测试**，不构成推荐油路尺寸或承载设计规则。

## 文件内容

输出目录由输入几何归一化 hash 和生成器版本确定，重复请求重用经哈希校验的成果；篡改文件会拒绝重用，不会静默覆盖。

每次生成：三零件 STEP/STL、装配 STEP、\`occt_side.svg\`、\`occt_end.svg\`、\`occt_projection.dxf\`、\`design_snapshot.json\` 和带哈希/几何检验摘要的 \`artifact_manifest.json\`。几何投影用 OCCT 隐藏线消除算法，从实际 B-Rep 抽取可见/隐藏边，再以折线近似写入 DXF/SVG。**这是实际三维几何的正投影线稿，不是具有公差/图框/剖面线的正式 GB/ISO 工程图，也不是实体剖切后的完整工程剖视图。**

用户确认状态在本模块不可写。输入出现 \`approval_state\`、\`confirmed_by\`、候选标记等未定义字段将被拒绝。

## 验收边界

CAD-02 当前阶段检验三个封闭有效实体、正体积、尺寸包围盒及同心、STEP 回读、DXF 零错误/零自动修复、三组基本参数、带孔/槽配置、缓存文件校验。GitHub Actions 单独运行 CAD-02 精确实体测试；浏览器界面此 PR 不添加 CAD-02 功能控件，后续再联调 API/三维渲染。第三方 FreeCAD/QCAD 人工互操作及专业油路规则审核仍需完成。
