# CAD-V2-06 本地 CAD 生成 API 验收

## 范围
- 新增独立的 \`bearing_cad/api.py\`；不修改 \`cad03_server.py\`、旧 CAD-02 路由或前端。
- 服务只能绑定 \`127.0.0.1\`。POST 要求同源 Origin、合法 Host、application/json，最大 16 KiB；拒绝重复 JSON 键、NaN、非法字段、伪造确认状态以及超额参数。
- 同步调用 \`generate_bundle\`，返回随机 128-bit job ID；短期进程内任务可查询，最多记录 128 条，重启后失效；不引入 Redis/Celery。
- \`POST /api/v2/cad/jobs\` 生成结果并返回 job URL；\`GET /api/v2/cad/jobs/{id}\` 查状态；\`GET /api/v2/cad/artifacts/{id}\` 查已校验 manifest 与下载链接；\`GET|HEAD /api/v2/cad/artifacts/{id}/files/{name}\` 安全下载；\`GET /api/v2/cad/status\` 查询能力。
- 单进程一个 OCCT 生成任务。超过资源预算或并发拥挤分别返回 422 RESOURCE_LIMIT 与 503 BUSY；不代表机械设计范围标准。
- 仅支持 \`rolling.deep_groove_ball\` + \`functional\`。其它轴承/精度等级显式 NOT_SUPPORTED。
- 下载入口验证 job ID、受控文件名、manifest/request hash 和每文件 SHA-256，异常不向 HTTP 客户端泄露内部堆栈。
- 这不是公网 API 或多用户认证服务；**禁止用反向代理公开暴露**。没有主 Agent 的审批权限。

## 本地启动
\`\`\`bash
python -m bearing_cad.api --port 8090 --artifacts artifacts/cad-v2
\`\`\`
使用现有 V2 契约 JSON，以同源 Origin 发起：
\`\`\`bash
curl -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8090' --data-binary @request.json http://127.0.0.1:8090/api/v2/cad/jobs
\`\`\`
其中 request.json 必须包含 PR-03 要求的全部显式几何参数，不根据型号猜测滚道或保持架。

## 门禁
- 单独隔离的 HTTP 7 项本地路由/安全测试已通过（本地以桩替代重型生成器，用于验证 HTTP 线路）；这**不等于**真实 CAD 集成通过。
- \`python -m unittest discover -s tests_v2 -p 'test_*.py' -v\` 应在 GitHub CadQuery 2.5.2 固定环境运行全部测试，新增测试包含真实 CAD STEP 生成、完整性校验、失败记录和并发限制。
- 旧 CAD-01/02/03/Workbench 回归仍须通过，方可合并。
- 非目标：PR-07 Web 工作台、PR-08/09 其它轴承、PR-10 二维图、PR-11 多 Agent Adapter、持久任务队列与真正多租户身份验证。
