# 滑动轴承 CAD 工作台：精确剖视与参数化图纸

本阶段提供同一 OCCT/B-Rep 几何源的装配 STEP、精确截面 STEP/STL、二维图纸 SVG/DXF。图纸为**带尺寸的方案复核图**，尚不是经过 GB/ISO 规范审核的制造图。

## Windows 本地运行

```powershell
git switch feature/cad-workbench-sectioned-model
npm ci
npm run build
conda activate bearing-cad02
python cad03_server.py --port 8088
```

打开 `http://127.0.0.1:8088/`，确认尺寸后选择生成，再切换完整装配/实体半剖模式。隐藏轴或座体可单独查看衬套供油孔与环槽。生成目录自动根据参数和版本区分。

## 核心实现

- `cad_workbench_drawing.py` 用 OCCT 与半空间求交，得到闭合的半剖实体，并根据真实剖切面的面边界生成剖面线。
- 端面图由原始 OCCT HLR 投影获得，图纸带 A3 风格图框、标题栏、关键结构和油路尺寸。DXF 采用 mm 单位，经过解析审计。
- 油孔固定方向和油槽形态仍是演示的几何约定，不是已验证的润滑设计推荐。
- 轴瓦和座体目前是名义尺寸接触，不代表已规定过盈或公差配合。

运行：
```powershell
python -m unittest discover -s tests -p test_workbench.py -v
```

人工验收需检查：STEP 包含三件零件；半剖 STEP 几何有效；图纸线型/剖面线/图签和尺寸对应当前参数；更改尺寸后旧结果失效；导出文件在 FreeCAD/QCAD 中打开。
