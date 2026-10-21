> 历史快照：2026-10-21起停止日常维护。最新目标与状态见 [plan.md](plan.md)，周报/每日交付见 [journal.md](journal.md)。下方保留迁移前记录，不覆盖新工作流。

# 候选任务池

更新：2026-10-21。昨日CI/制品与今日方案A均已验收。今日任务、实际结果及完整SHA见 [10-21 daily](daily/2026-10-21.md)，旧交付见 [10-20 daily](daily/2026-10-20.md)。

| ID | 优先级 / 状态 | 任务 | 价值与验收 | 依赖 / 边界 |
| --- | --- | --- | --- | --- |
| PACK-01 | 已验收 | Python制品完整性 | backend/pipelines/shared、迁移资源，独立安装后6入口导入 | 原缺包及POSIX symlink修复保留 |
| ENG-01 | 已验收 | 后端CI | Linux锁定安装/Ruff/256测试/wheel导入通过 | 普通CI无真实服务 |
| ENG-02 | 已验收 | 前端CI | Node22/npm ci/lint/types/35测试/build通过 | 生产build不代表公网发布 |
| ENG-03A | 已验收 | API/worker共镜像 | Python3.12/uv0.11.8、wheel安装、非root、已安装迁移资源 | Linux实际构建；本机下载受阻 |
| ENG-03B | 已验收 | Next standalone镜像 | Node22、静态资源、非root、浏览器公开API build URL | Linux容器HTTP/资产实测；改URL须重建 |
| ENG-04 | 已验收（测试依赖） | 独立完整编排 | 迁移→5SKU seed→存储/API/web；worker显式选择并初始化/停止；重复init与失败阻断恢复 | 新项目/卷，旧环境未操作；非真实业务验收 |
| ENG-05A | 已验收 | 交付验证说明 | verification/README与逐增量交接、运行手册 | 实际结果分本地/远端记录 |
| ENG-05C | 已验收 | 测试provider启动smoke | 固定1024维成功/768维拒绝、auth/空dashboard/CORS/资产、init失败阻断API/worker及恢复、仅清理自有项目 | 无真实模型；不替代ENG-05B/浏览器E2E |
| ENG-05B | P0 / 候选 | 真实业务交付烟测 | 隔离演示数据/provider、Ask引用/报告、真实启动和效果证据 | 确认服务、调用/预算、凭据提供方式 |
| LOCAL-01 | P1 / 环境待复跑 | 本机容器下载与复验 | Docker Hub/ECR可达后重跑同一smoke | 不改全局网络/TLS配置；不重复称Linux通过为本机通过 |
| ENG-06 | P1 / 候选 | 真实E2E跨平台 | 移除Playwright Windows固定路径，专用DB/collection、明确人工门禁 | ENG-05B及真实调用范围 |
| DEMO-01 | P1 / 候选 | 公网方案 | 域名/资源/预算/HTTPS/访问限制/回滚可审阅 | 不自动发布或购买资源 |
| AI-01 | P1 / 候选 | 真实评测 | 样本/环境/指标/效果/成本/局限可复核 | 真实链路与调用成本 |
| AI-02 | P1 / 候选 | 周报证据持久化 | report/claim到mention快照与范围，单列ADR | 不把Ask引用当周报关联；单独确认schema |

ENG-03原任务拆为03A/B，ENG-05C显式限定测试依赖，不以其验收替代真实ENG-05B。今日6个实现/修复提交与交接文档按价值边界推送，不为4–5目标机械拆分。两次真实容器失败（MinIO拉取、internal端口）已保留并修复；最终三项CI成功见daily。

今日A无剩余功能任务。后续候选需另行确认；真实模型、付费、凭据配置、演示数据与公网发布没有本轮新授权。任务完成后保留历史与证据，不删除未验证边界。
