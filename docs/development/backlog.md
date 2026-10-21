# 候选任务池

更新：2026-10-21。昨日方案 A 的 PACK-01、ENG-01、ENG-02、ENG-05A 均已验收；今日候选仍待确认，见 [10-21 daily](daily/2026-10-21.md)。已完成范围、完整 SHA 与验收见 [10-20 daily](daily/2026-10-20.md)。

| ID | 优先级 | 任务 | 价值与验收 | 依赖 |
| --- | --- | --- | --- | --- |
| PACK-01 | 已验证 / P0 | Python 制品完整性 | wheel 覆盖 backend/pipelines/shared 和迁移资源；锁定新环境安装后导入通过 | 本地验证完成；代码与 Linux symlink 修复见 daily |
| ENG-01 | 已验证 / P0 | 后端 CI | Linux 锁定安装、Ruff、244 测试与安装后导入全部通过；首次失败及修复有记录 | PACK-01；POSIX 回归与最终 smoke 通过 |
| ENG-02 | 已验证 / P0 | 前端 CI | Node 22、npm ci、lint、next typegen + typecheck、35 测试、生产构建；首次远端通过 | 已推送；最终 SHA 见 daily |
| ENG-03 | P0 / 待确认 | API/worker/前端镜像 | 拆 ENG-03A Python 共镜像、ENG-03B Next standalone；实际构建/非 root/资源导入，公开 API build URL 不使用容器 DNS | PACK-01 已验收；Docker 常规环境可连接，下载/构建未验证 |
| ENG-04 | P0 / 待确认 | 完整服务编排 | 独立项目/卷/collection；迁移→基础 seed→SKU/Milvus/embedding 校验；worker 显式 profile；重复 init 和失败阻断实测 | ENG-03；禁止复用根 Compose 固定容器名与旧数据 |
| ENG-05A | 已验证 / P0 | CI 验证入口和故障定位说明 | verification.md、README 入口与最终 daily 回填已完成，10 文件本地链接检查通过 | PACK-01、ENG-01/02 的实际执行结果 |
| ENG-05B | P0 | 完整交付烟测 | 从零启动、登录、仪表盘、Ask 引用/报告流程真实可复跑 | ENG-04；隔离服务与 provider 授权 |
| ENG-05C | P0 / 待确认 | 测试 provider 下的容器启动烟测 | 1024 维成功/768 维失败、init 失败阻断、health/auth/dashboard/web 静态资源与重复初始化；不跳过生产启动检查，不冒充真实 Ask 效果 | ENG-04；仅测试 profile，外部模型访问受限；不替代 ENG-05B |
| DEMO-01 | P1 | 公网演示设计 | 域名、资源、预算、HTTPS、访问限制及回滚方案可审阅 | 确定部署预算 |
| AI-01 | P1 | 真实链路评测基线 | 样本、环境、执行方式、指标及局限可复核 | 核实服务与调用成本 |
| AI-02 | P1 | 周报结论证据持久化设计 | 明确 report/claim 到 mention 的快照和范围，不把 Ask 引用当作周报关联；单列 ADR 与验收 | 单独确认 schema/产品范围 |
| ENG-06 | P1 | 真实 E2E 跨平台与手工门禁 | 移除 Playwright 对 Windows Python 路径的依赖；专用 DB/collection；无凭据默认不调用 | ENG-04/05B；后续明确确认 |

ENG-05 原拆为 ENG-05A（无需服务的交付说明）与 ENG-05B（真实应用烟测），保留原目的。10-21 新增 ENG-05C 明确测试依赖下的启动验收，不用其取代 ENG-05B。ENG-03 以已完成 PACK-01 为前置；本机 Docker 常规环境已可连接，容器尚未验收。10-19 待决策事项已合并；昨日方案 A 已验收，今日范围未确认。

ENG-01/02 排障记录：早间沙箱 pytest/build 无有效通过结果；常规环境和 Linux 已实际通过。另发现并修复安装烟测对 Linux venv symlink 的处理错误。当前门禁验收有实际运行支撑；真实服务烟测 ENG-05B 仍未验证。

每日选出可完成范围，补充工作量和提交边界。确认后标记进行中，并链接当日日志；完成时填写提交与验证，不直接删除任务历史。

10-21 推荐 ENG-03A/B + ENG-04 + ENG-05C，约 6–9 小时；备选仅镜像 3–5 小时。目标 4–5 个独立有价值提交，今天规划阶段仍为 0。真实模型调用、付费/凭据配置、演示数据和公网发布均未获新授权；周报证据关联 AI-02 与真实评测 AI-01 延续，不为岗位索引中的新框架名扩展当日范围。

### 21:20 用户确认今日方案 A

用户在本聊天明确确认 ENG-03A/B、ENG-04、ENG-05C。状态转为开发中；真实模型/付费/凭据配置/公网发布不在范围。启动契约记录于 docs/development/decisions/0001-container-startup-contract.md，实际验证与提交逐增量追加。
