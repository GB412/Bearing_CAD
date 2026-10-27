# CAD-V2-09B 三类轴承统一工作台：审查与验收

## 代码审阅基线
- 审阅基线 main `0161f75472d220678e4962cace195eecbcd19e0d`，PR-18 已合并，三类轴承核心建模、STEP 往返和旧工作流在 GitHub 固定环境通过。
- 前后端功能不一致：后端支持 deep_groove / cylindrical / angular_contact，`rolling_workbench.js`、`rolling_manifest.js` 原先只发深沟球请求。
- 现有状态失效逻辑对数字输入处理较好，但切换保持架、恢复参数没有取消进行中的请求；会出现旧结果与当前表单不一致的风险。
- `BuilderRegistry` 存在但并非实际成果路径的必要依赖；本 PR 不额外引入 registry、框架、多种 API 或新的 CAD 生成算法。

## 本次变更
- 单一 `rolling.html` 工作台提供深沟球 / 圆柱滚子（N、NU、NJ、NF、NUP） / 角接触三类选择。
- `rolling_manifest.js` 在一个配置表中保存用户可编辑的显式几何测试夹具；参数均以 mm 输入，接触角以度输入。选择类型后动态展示与对应后端契约一致的字段，不做型号派生或 CAD 算法。
- 请求仍遵循 `bearing-cad.request.v1`，CageSpec 只允许深沟球。其他两类页面直接隐藏不支持的保持架设置，manifest 使用后端的 CAGE_OMITTED。
- 保留 STEP/STL、零件实例树、透明、可视剖切、爆炸与下载功能。NUP 独立挡圈由现有 manifest 动态绘制。
- 类型切换、数字输入、挡边构型切换、保持架开关、重置参数均取消旧请求并清空失效视图。
- 旧静态页面路径、本地同源 CAD API、滑动轴承页面与所有后端建模器均不更改。

## 验收
- Node 合同测试覆盖三个真实请求形状、N/NU/NJ/NF/NUP 配置、有限数字、接触角输入、保持架不支持与 URL 白名单。
- Playwright 使用 API 格式的模拟 STEP 成果清单验证 NUP（14 件）、角接触（13 件）、深沟球和动态切换后模型实例与请求参数一致、开关及时清除旧状态。
- 必须通过 GitHub CAD-V2 Python/OCCT、rolling-ui Node+Vite、CAD-01 Playwright 及 CAD-02/03/Workbench 回归。模拟浏览器结果不替代真实 CadQuery/OCCT 与人工 CAD 核验。

## 范围限制
- 示例尺寸仅是几何夹具，不是厂家样本或制造推荐值。没有新增保持架、滚道修形、接触力学、二维工程图或多 Agent。
- 异步加载、产品身份认证及生产级队列不是本地单用户工作台职责。
- 提交新的 `feature/cad-v2-09b-unified-rolling-workbench` PR，待审查不自动合并 main。之后独立推进 CAD-V2-10 二维图纸。
