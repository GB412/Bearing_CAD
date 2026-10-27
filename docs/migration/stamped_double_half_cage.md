# 3D-MIG-04 RoBAS 深沟球两片冲压保持架与铆钉几何

原始依据：`RoBAS/BearingModel/Cage/StampingCage.cs:199–305`。原 C# 用球形差集构造冲压半笼，在球间半相位处生成穿过半笼的铆钉，再镜像第二片。新代码 `bearing_cad/stamping.py` 复用了此建模思路，并创建**两片独立 B-Rep 和 Z 个独立铆钉实例**，而非用单件笼体替代。

## 显式参数要求
深沟球请求可选 `cage.kind=stamping_double_half`，必须显式指定原共用的 `inner_d_mm, outside_d_mm, width_mm, pocket_clearance_mm`，额外必填 `board_thickness_mm, rivet_shaft_d_mm, rivet_head_d_mm, rivet_hole_clearance_mm`。宽度包括两片冲压件及两端半球形铆钉帽，不使用型号推导。
- 两片笼体分别布置在 Z 的上/下半空间，球心位于 Z=0，窗口以球半径+指定余量切出真正球面凹槽。
- Z 个铆孔位于相邻钢球中间角位置；铆钉由长杆和两端半球帽融合而成，铆孔与杆之间保留输入间隙。
- 拒绝与肩部径向冲突、连接板厚不足、铆钉头超出笼体径向带或轴向总宽大于轴承宽度；检查内外圈/球/笼片/铆钉非预期实体干涉。
- 默认深沟球旧请求仍无笼，既有 `simplified_annular` 简化保持架继续可选。
- 生成器版本号升级，避免新的双半笼成果与旧文件缓存哈希混淆；manifest 标记 `STAMPING_DOUBLE_HALF`，26 件总装包含内圈+外圈+11 钢球+2 半笼+11 铆钉。

## 与 RoBAS 的关键差异
这个实现**不是**原版 Eyeshot 几何逐点复现：C# 部分冲压板厚与球径按照型号选取、铆钉孔加工表达由内部函数派生，新接口要求全部几何尺寸显式。用户必须自己提供来源合理的数值，不能将默认夹具视为制造设计。保留旧 3D 模型完整度状态和工程未审核限制。

## 自动验收
`tests_v2/test_stamping_cage.py` 三尺度、球-铆钉相位、两半笼互不重叠、穿孔/局部有效、STEP 中 26 实体全数回读有效、manifest SHA 与不同请求缓存隔离；旧深沟球无笼与简化笼回归。必须 GitHub 全套 CAD-01/02/03、V2 和 Workbench CI 通过后合并。

**尚待专业审核**：真实型号对应的板厚与铆钉规范、预载和寿命、原 Eyeshot STEP 体积/轮廓等价、网页详细笼体输入 UI。当前属具备原始构造层级的功能级 CAD 迁移，不是制造认证。

## 3D-MIG-08A 参数语义澄清
当前 `board_thickness_mm` 并**不是生成的冲压板精确厚度**。它约束 `half_height > ball_radius + pocket_clearance_mm + board_thickness_mm`，属于球兜外的最小轴向余料限制；实际半笼由环形坯减去球形球兜形成，局部厚度随几何位置变化。网页现显示“球兜外最小轴向余料约束”，保留 JSON 字段名称以兼容现有保存的参数。
对于需要精确冲压板厚的制造模型，必须另经专业设计验证，不能将该字段理解为材料板厚。
