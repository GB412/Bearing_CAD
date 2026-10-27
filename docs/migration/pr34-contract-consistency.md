# PR34 参数契约与约束语义收口

- 全部入口（`parse_request`、HTTP API、`generate_bundle`）仅接受功能级 `detail_level="functional"`。暂不实现 detailed/envelope，拒绝虚假支持。
- 单项几何尺寸资源上限 1000 mm，球/滚子数量上限 64，**保持架所有尺寸同样由 `parse_request` 处理**；HTTP 保留总请求体与并发防护及资源预算兜底。对于直接通过 dataclass 构造的非正常请求，`generate_bundle` 在触发几何计算前重新经过参数解析。
- 圆柱滚子的 `axial_clearance_mm` 保留为**每侧要求的最小轴向余量**，不再以“实际几何间隙”误导。若改变该值而仍满足几何承载空间，滚子的长度和 Z 中心保持不变，STEP 几何可以相同；`request_hash` 会变化以记录要求差异。
- 已有 C# RoBAS 功能级迁移和 OCCT 结构公式一律不改。修改仅涉及 Python 输入边界、前端标签、文档与测试。
- 额外修正深沟球、圆柱 builder 在**手动构造 BearingRequest** 情况下对非 functional 的保护。仍由公共 parse_request 作为正常入口。
- 测试：三轴承及全部保持架拒绝非功能级，超大笼尺寸在解析阶段拒绝；宽度不变时仅修改最小余量不改变实体；超出实际可用余量严格拒绝；绕过 parser 的伪造 dataclass 也不能通过生成。
