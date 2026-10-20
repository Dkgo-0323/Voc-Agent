# 候选任务池

更新：2026-10-20。方案 A 的 PACK-01、ENG-01、ENG-02、ENG-05A 均已实现并验收；其余仍为候选。范围、完整 SHA 与验收见 [10-20 daily](daily/2026-10-20.md)。

| ID | 优先级 | 任务 | 价值与验收 | 依赖 |
| --- | --- | --- | --- | --- |
| PACK-01 | 已验证 / P0 | Python 制品完整性 | wheel 覆盖 backend/pipelines/shared 和迁移资源；锁定新环境安装后导入通过 | 本地验证完成；代码与 Linux symlink 修复见 daily |
| ENG-01 | 已验证 / P0 | 后端 CI | Linux 锁定安装、Ruff、244 测试与安装后导入全部通过；首次失败及修复有记录 | PACK-01；POSIX 回归与最终 smoke 通过 |
| ENG-02 | 已验证 / P0 | 前端 CI | Node 22、npm ci、lint、next typegen + typecheck、35 测试、生产构建；首次远端通过 | 已推送；最终 SHA 见 daily |
| ENG-03 | P0 | API/worker/前端镜像 | 可复现构建，包含全部运行源码，不含本地密钥与产物 | 核实运行包及依赖 |
| ENG-04 | P0 | 完整服务编排 | 迁移→基础 seed→SKU/Milvus/embedding 启动校验；专用环境实测，不改旧数据 | ENG-03；Docker daemon 恢复 |
| ENG-05A | 已验证 / P0 | CI 验证入口和故障定位说明 | verification.md、README 入口与最终 daily 回填已完成，10 文件本地链接检查通过 | PACK-01、ENG-01/02 的实际执行结果 |
| ENG-05B | P0 | 完整交付烟测 | 从零启动、登录、仪表盘、Ask 引用/报告流程真实可复跑 | ENG-04；隔离服务与 provider 授权 |
| DEMO-01 | P1 | 公网演示设计 | 域名、资源、预算、HTTPS、访问限制及回滚方案可审阅 | 确定部署预算 |
| AI-01 | P1 | 真实链路评测基线 | 样本、环境、执行方式、指标及局限可复核 | 核实服务与调用成本 |
| AI-02 | P1 | 周报结论证据持久化设计 | 明确 report/claim 到 mention 的快照和范围，不把 Ask 引用当作周报关联；单列 ADR 与验收 | 单独确认 schema/产品范围 |
| ENG-06 | P1 | 真实 E2E 跨平台与手工门禁 | 移除 Playwright 对 Windows Python 路径的依赖；专用 DB/collection；无凭据默认不调用 | ENG-04/05B；后续明确确认 |

ENG-05 拆为 ENG-05A（无需服务的交付说明）与 ENG-05B（真实应用烟测），保留原目的。ENG-03 下一增量以 PACK-01 为前置；本机 Docker 不可用，不承诺今日容器验收。10-19 待决策事项已合并；方案 A 已验收，其余范围未确认。

ENG-01/02 排障记录：早间沙箱 pytest/build 无有效通过结果；常规环境和 Linux 已实际通过。另发现并修复安装烟测对 Linux venv symlink 的处理错误。当前门禁验收有实际运行支撑；真实服务烟测 ENG-05B 仍未验证。

每日选出可完成范围，补充工作量和提交边界。确认后标记进行中，并链接当日日志；完成时填写提交与验证，不直接删除任务历史。
