# 当前仓库状态

最后更新：2026-10-21 20:58（北京时间）。阶段：**昨日 CI/制品方案 A 已验收；今日镜像与编排方案 A 已确认，实施中**。今日范围和检查见 [10-21 daily](daily/2026-10-21.md)，昨日完整 SHA 和验收回填见 [10-20 daily](daily/2026-10-20.md)，操作说明见 [验证入口](verification.md)。

## 已有能力

依据 README、应用入口、Compose、前端脚本、Phase 15 交接及 10-18 代码增量：已有 FastAPI、异步 PostgreSQL、Milvus、Next.js、受控 Agent、SSE、Ask 引用、报告与评测工具。周报尚无持久化评论引用关联。本轮离线检查结果在 daily 回填，历史交接成绩不代替当前验证。

## 交付现状与剩余缺口

- 根 Compose 只编排存储依赖，未形成 API、worker、前端完整运行闭环。
- 已新增双端 `.github/workflows`；Windows 干净安装验证通过，Linux 最终双端 CI 通过。后端首次烟测失败的解释器 symlink 缺陷已修复并增加回归，失败历史保留在 daily。
- 生产 CORS 配置含占位域名；现有身份边界为单密码/JWT，浏览器 localStorage 存 token。
- 尚未形成已验证公网部署闭环。
- wheel 缺少 pipelines/shared 的问题已通过实际构建复现并修复；独立锁定环境中安装后导入通过，Linux 最终检查结果见 daily。
- API 启动依赖已迁移和 seed 的 DB、Milvus 及真实 embedding 维度探测；现有健康端点不能单独证明离线启动。
- 10-21 常规环境只读查询 Docker 服务成功（29.1.3）；沙箱 pipe permission denied 不代表 daemon 停止。镜像和完整编排尚未执行验收。Playwright 启动 API 命令是 Windows 路径，不能直接当 Linux PR CI。

## 当前工作

- 每日独立调研和规划任务已配置：北京时间 12:00，任务 ID `voc-agent`。
- 10-19 已完成配置及文档组织，无功能提交；10-20 首次独立运行已核验 3 条官方校招 JD 和 2 个开源项目具体版本/文件。
- 用户已在本聊天确认并完成 A：排障、双端 CI、Python 制品完整性和验证说明；镜像/编排顺延。
- 当前结果：Ruff 通过；锁定新环境后端 243 项测试通过；干净前端 npm ci、lint/typecheck、35 项测试和 Turbopack build 全通过。隔离测试入口避免本地 .env/应用变量污染。早间沙箱构建失败在正常进程环境未复现，无须换构建器；pytest 特定沙箱阻塞根因仍未知。
- 已将四个实现提交推送 main，运行代码 HEAD 为 `892917aa2765e6244deac25501bdc6438149aa6b`；Linux 最终后端 **244 passed**，前端 **35 passed + build 通过**，双端 job 均成功。交接文档独立提交，完整 SHA 与 CI 链接见 daily。无功能部署或真实 provider 调用。

## 工作区与交接

配置前已存在未跟踪项：`artifacts/runtime/`、`docs/interview_mock_exam_voc_agent_reverse_engineering.md`、`docs/resume_project_analysis.md`，不得混入后续提交。原始 `docs/career_engineering_plan.md` 也尚未提交。

10-20 运行起点：`main` / `652a26a08012d6b739ca4a69955517a52a5eb7cd`。当前已推送四个实现提交及收尾文档，精确 HEAD 以下次 `git status` / `git log` 为准。原本未跟踪的开发入口、模板、10-19 daily、decisions 入口仍保留，不混入本次提交。可见列表未发现其他同仓库活跃开发，仍须在编辑和暂存前复查。

下一次运行需重新检查分支、HEAD、工作区和进行中的开发，不能沿用这份快照假定工作区未变。优先续接已确认未完成事项；昨日方案 A 已完成，下一阶段镜像/编排及公网发布仍需另行确认范围。

## 10-21 规划与复核

- 本地及 GitHub main 均为 `359befd009f72692abf5e1746cf17a25f7608354`，今日重新核实该提交的昨日双端 CI 均 success。可见同仓库其他聊天空闲，开发前仍需复查。
- 今日常规环境隔离后端测试 **243 passed / 1 skipped / 3 warnings**；Ruff 通过。沙箱全量测试无输出后中止，未冒充通过；前端、制品及容器没有重跑。
- 推荐今日 A：ENG-03A/B 双端镜像、ENG-04 独立编排、ENG-05C 使用测试 provider 的启动烟测，约 6–9 小时。worker 默认不启用，独立卷/collection、回环端口；不调用真实模型、不发布。等待本聊天明确确认，未进行开发/暂存/提交/推送。
- ENG-05C 不替代 ENG-05B 真实业务验收；岗位研究只有官方索引线索，动态详情正文未完整取得，来源与边界见今日 daily。此前 Docker 不可连接属于昨日快照，不再当今日阻碍。

### 21:20 用户确认今日方案 A

用户在本聊天明确确认 ENG-03A/B、ENG-04、ENG-05C。状态转为开发中；真实模型/付费/凭据配置/公网发布不在范围。启动契约记录于 docs/development/decisions/0001-container-startup-contract.md，实际验证与提交逐增量追加。
