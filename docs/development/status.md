# 当前仓库状态

更新：2026-10-21。**今日方案 A 已完成并通过 Linux 实际验收**；完整 SHA、失败修复与命令见 [10-21 daily](daily/2026-10-21.md)。操作见 [验证入口](verification.md)、[容器手册](../../ops/README.md)；架构边界见 [ADR 0001](decisions/0001-container-startup-contract.md)。

## 已有能力与今日交付

- FastAPI、异步 PostgreSQL、Milvus、Next.js、受控 Agent、Ask SSE/引用、报告与评测工具已存在；周报仍无逐结论持久化 mention 关联。
- 10-20 已验收 wheel 完整性与双端 CI。10-21 交付非 root API/worker 共镜像、Next standalone、独立 ops 编排和测试 provider 下的完整启动/失败恢复 smoke。
- ops 不使用根 Compose 的固定容器名/旧卷；一次性迁移/基础 seed 成功后才允许 API/可选 worker 启动，worker 默认关闭。API 在 smoke 中仅连接 internal 网络，测试专用固定目标入口发布回环端口；普通编排不增加网关。
- 新环境旧 MinIO 镜像不可拉取，按 Milvus 官方快照改用维护镜像，Linux 实测兼容当前 Milvus；根配置、旧四个 voc_* 容器及旧数据没有被操作。

## 实际验收与限制

- 已推送代码 HEAD `3e7bbfadb99ec1301b86ead978e8b011cc432b70`：[容器CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39611578027)、[后端CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39611578134)、[前端CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39611578261)均 success。已读取实际 job 日志。
- Linux 后端 **256 passed /4 warnings**，wheel 安装后6入口导入通过；前端 **35 passed + build**。Windows 最终隔离后端 **255 passed /1 skipped /3 warnings**；前端 lint/typecheck/35测试/生产build通过，POSIX用例由Linux执行。
- 容器验收：双端构建、非 root/迁移资源、DB迁移/5SKU seed、Milvus/1024维探测、health/auth/空dashboard/CORS/web JS/CSS及公开URL、重复init、内部网络、可选worker初始化/停止、768维启动拒绝、init失败阻断API/worker、恢复成功；仅清理本次随机测试项目。
- 本机 Docker 29.1.3 可连接，但 Docker Hub/ECR 基础镜像下载失败。容器成功证据来自 Linux CI，**未声称本机已能复跑**；网络改善后可按手册重跑。
- 测试 provider 只提供固定向量；没有真实模型、真实业务数据、Ask/报告效果、周期任务执行、Playwright浏览器交互或公网部署验收。原两次失败及修复有记录，没有改写成通过。

## 后续候选

今日 A 无剩余实现任务。下一阶段可讨论 ENG-05B（真实provider/数据/Ask/报告）、ENG-06（真实E2E跨平台）、AI-01（真实评测）与 AI-02（周报证据关联）。真实调用/预算/凭据配置和公网发布需另行明确，不沿用本次测试范围授权。

公网前仍需生产 CORS、HTTPS、访客权限/限额、资源预算、凭据与回滚方案。前端 API URL 在构建时固化，换域名须重建；可选worker单进程约束不是全局分布式锁。

## 工作区交接

本次6个实现/修复提交已正常推送 main；最后运行手册与验收文档单独提交，其自身SHA由git log及最终聊天/自动化memory提供，避免自引用。仅按具体路径暂存；原有 artifacts/runtime、career_engineering_plan、面试/简历材料、development README/10-19 daily/templates/decisions README 均保留，未混入。新聊天先复查git/远端/活跃开发状态，不能沿用本快照假定工作区未变。
