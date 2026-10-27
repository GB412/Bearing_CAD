# 3D-MIG-05 · 三类轴承详细保持架接入统一三维工作台

## 范围与问题
基于 `main@c84cfd1a77b762a3d0e867d7e64e1cced1ff415a`。PR #21/#22/#23 已实现 OCCT 精确保持架，但旧 `rolling_manifest.js` 仅允许深沟球简化笼、圆柱和角接触 `hasCage=false`，且 `rolling.html` 显示不准确的“不支持”说明。**本 PR 只打通前端参数契约与已有后端建模器，不修改任何 CAD 几何算法、制造规则或 API。**

## 支持的网页配置
| 轴承 | 保持架选项 | 几何夹具 | 11 个滚动体时实例数 |
| --- | --- | --- | --- |
| 深沟球 | 无 / simplified_annular（默认） | 48/60/11 mm, 余量 .25 mm | 13 / 14 |
| 深沟球 | stamping_double_half | 48/60/11.5 mm, 余量 .15 mm, 板厚 .7 mm, 铆钉杆 1 mm/头 1.6 mm/孔余量 .05 mm | 26 |
| 圆柱滚子 NU | 无（默认） / cylindrical_window | 52.6/55.4/16 mm，余量 .15 mm | 13 / 14 |
| 圆柱滚子 NUP | 无（默认） / cylindrical_window | 同上，另外保留独立活动挡圈 | 14 / 15 |
| 角接触球 | 无（默认） / straight_pocket | 51/57/11 mm，余量 .15 mm | 13 / 14 |

所有夹具数值严格对应前期 `tests_v2/test_cylindrical_cage.py`、`test_straight_pocket_cage.py`、`test_stamping_cage.py` 的**几何测试输入**，不是推荐生产尺寸。窗口余量是概念几何净距，不是制造公差。

## 本次实现和兼容性
- 一处 `cageForms` 定义每种保持架的必需字段、中文标签和默认测试值；仅增加必要的 kind 选择及输入字段，不增加新 UI 框架或后台生成流程。
- 通过 `bearing-cad.request.v1` 严格发出显式 `cage.kind`，仍支持旧版深沟球简化笼调用时省略 kind；其他组合、未知字段、空字段、非有限/非正数必须拒绝。
- `cageEnabled` 布尔开关仍保留，以兼容已有浏览器操作；新增 `cageKind` 下拉。切换类型/笼体/尺寸时立即终止旧请求并清空旧模型。深沟球仍默认简化笼，圆柱/角接触默认无笼。
- 浏览器仍从实际后端 manifest 获取原型 STL + 装配实例；双半笼 2 件和铆钉 11 件是独立实体，零件树可逐实例显隐，装配爆炸时两半笼往相反轴向分离。
- 不修改旧滑动轴承页面、OCCT 圈体/滚道/保持架建模器、STEP 文件格式、HTTP 回环/安全边界与成果缓存。

## 验收与证据范围
- Node 参数契约测试：三轴承/四笼体、N/NU/NJ/NF/NUP 兼容、非法笼体/字段/尺寸、旧简化笼向后兼容。
- Playwright：无保持架/有保持架、NU/NUP/角接触/深沟球双半笼 26 实例、两片笼体及 11 个铆钉显隐和爆炸、切换旧模型失效。
- GitHub CAD-V2 Python/OCCT 门禁：原有真实带笼 STEP 全数实体回读及拓扑/干涉检查；CAD-01 浏览器、CAD-02/03 与 Workbench 原功能不退化。
- 浏览器测试用模拟 HTTP/三角网格验证界面契约，**不能独立证明真实 CAD 内核与浏览器已经在同一测试中端到端通过**。人工使用 FreeCAD 检查 STEP、实际 3D 视觉效果、制造尺寸/公差审核另列 3D-MIG-06/07。

## 手动运行
```powershell
git switch main
git pull --ff-only origin main
npm ci
npm run build
python -m bearing_cad.api --port 8090 --static dist
```
打开 `http://127.0.0.1:8090/rolling.html`，选择轴承类型并勾选保持架，选择相关 kind，输入测试参数生成 STEP/STL。
