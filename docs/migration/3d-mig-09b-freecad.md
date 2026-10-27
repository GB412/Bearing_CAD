# 3D-MIG-09B：FreeCAD STEP 导入与人工工程观察验收

> **当前状态：验收脚本/记录方案就绪；FreeCAD 人工实际运行仍 PENDING。** 本工作流不会因为现有 OCCT CI 通过就将下表改成“通过”。这不是原版 Eyeshot 等价验证，也不是制造校核。

## 从真实 CAD API 复现 7 组独立 STEP

安装与 `environment-v2.yml` 一致的 Python/CadQuery 环境，并在仓库根目录执行：

```powershell
python -m bearing_cad.migration_baseline --output build/migration-07a
```

`build/migration-07a/comparison.json` 记录每个案例的 `artifact_key`。对应文件：

```
build/migration-07a/bundles/<artifact_key>/bearing_assembly.step
build/migration-07a/bundles/<artifact_key>/artifact_manifest.json
build/migration-07a/bundles/<artifact_key>/design_snapshot.json
build/migration-07a/bundles/<artifact_key>/geometry_quality.json
```

**用户电脑需安装 FreeCAD（项目不代装），并自行启动图形界面。** FreeCAD 主界面打开 Python 控制台（菜单“视图 → 面板 → Python 控制台”，名称可能随版本变化）后输入：

```python
exec(open(r"D:\\RotorStudio\\BearingCAD_Demo\\scripts\\freecad_step_review.py", encoding="utf-8").read())
```

将上述路径替换为实际仓库路径，选择一个 `bearing_assembly.step`。脚本会通过 FreeCAD STEP 导入器打开文件、核查实测实体有效性/数量/整体包围，生成同目录 `freecad_import_review.json`，同时将 3D 视图切到轴测图。

**注意：该脚本从未在本开发环境的 FreeCAD 中运行，因为此环境没有 FreeCAD。** 因此它属于待本地验收的脚本，不是已经通过的第三方软件验证。不同版本的 STEP 导入分组方式可能导致导入对象统计与原装配清单不同，出现差异时必须人工确认，不应直接忽略。

## 各型号人工检查清单

| 案例 | 可打开 STEP | 完整独立零件 | 主体尺寸与位置 | 内部结构观察 | 截图 / FreeCAD 版本 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| dgb_no_cage | □ | □ | □ | □ | — | NOT_RUN |
| dgb_stamped | □ | □ | □ | □ 双半笼及 11 铆钉 | — | NOT_RUN |
| crb_NU_window | □ | □ | □ | □ 窗孔保持架 | — | NOT_RUN |
| crb_NUP_window | □ | □ 活动挡圈独立 | □ | □ 挡边与挡圈 | — | NOT_RUN |
| acb_15deg | □ | □ | □ | □ 非对称肩部 | — | NOT_RUN |
| acb_25deg_window | □ | □ | □ | □ 径向窗孔 | — | NOT_RUN |
| acb_40deg | □ | □ | □ | □ 非对称肩部 | — | NOT_RUN |

工程观察与数据追溯需要保存：检查日期、操作员、FreeCAD 版本、所打开 STEP 路径、文件 SHA-256/成果 ID、导入报告、轴测图/剖视截图、存在的偏差和处理 PR 链接。

## 验收范围与发布声明
- 只有实际打开 STEP 并留存上述证据，才能将某案例的状态改成 `PASSED`。
- 单凭 `freecad_import_review.json` 自动检查通过，仍是 `AUTOMATED_IMPORT_CHECK_ONLY_MANUAL_REVIEW_PENDING`。
- GUI 目视检查不能代替量具/试验、符合 GB/ISO 公差、承载力寿命或制造批准。
- 09C 可以交付**可复现功能级三维演示版本（有 FreeCAD 人工验收待办）**；需要宣称“09B 全部完成”则必须提供本地 FreeCAD 实际审核证据。
