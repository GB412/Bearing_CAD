# CAD-V2-01 接口与 CAD 内核门禁验收

## 范围
- 新增独立 `bearing_cad` 包，契约与注册器不导入 CadQuery/OCP。
- 三种滚动轴承类型仅具备严格 schema 校验。未注册建模器必须返回 `NOT_SUPPORTED`，尚不能生成滚动轴承。
- 支持仅显式输入的几何参数；不启用未经工程审核的 RoBAS 派生公式。
- 新增一个**非轴承** 4×3×2 mm 实体的 OCCT STEP 导出/回读探针。
- 保持旧 CAD01/02/03 应用与测试文件不变；不集成 HTTP/UI/Agent。

## 实际测试（开发环境）
- 开发环境：Python CAD 环境中的 CadQuery 2.8.0 / OCP 7.9.3.1；与 CI 计划固定版本不同。
- `python -m unittest discover -s tests_v2 -p 'test_*.py' -v`：6 tests, OK，包括真实 STEP roundtrip。
- `python -m compileall -q bearing_cad`：完成。
- 额外检查：仅 `import bearing_cad` 不加载 CadQuery/OCP。
- GitHub Actions：本 PR 新建 `cad-v2.yml`（Python 3.11 / CadQuery 2.5.2，必须待远端实际执行后核查；此文档不宣称远端已通过）。
- 未在本环境独立运行旧滑动轴承全部回归；旧 CAD 工作流文件未修改，合并前核对远端 CI。

## 已知边界
- 仅测试输入基本有效性（有限正尺寸、d<D、d<节圆<D、数量及类型）；沟道的真实可制造几何及装配干涉由 CAD-V2-03 校验。
- `ComponentDefinition.shape` 是不依赖 OCCT 的不透明对象；真正几何验证待 CAD-V2-02。
- 当前组装实例主要支持沿 Z 旋转和毫米平移；必要的任意姿态支持在建模阶段补充，不提前抽象。
- 本 PR 不迁移 RoBAS 原始 C# 或商业 DLL。
- 后续 CAD-V2-02 需从最新合并后的主分支开发；确认 CI 采用的固定环境真实通过后才能进入。
