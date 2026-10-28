# VOC Agent 开发记录

按北京时间、ISO周组织周报与日更；当前目标/优先级只维护 [plan](plan.md)，运行入口见 [根README](../../README.md)。保留已确认决定和真实交付，不复制三份状态表。

## 2026-W44（10-26 至 11-01）

### 周一研究与本周方案（2026-10-26）

访问日期均为2026-10-26。此次重新检索官网；下列证据不是三条实时完整JD验收。搜索索引有正文但详情页动态渲染返回零行时，只记录官网索引证据，不将搜索抓取时间当岗位发布日期、不确认实时名额。同企业样本有偏差，不外推整个校招市场。

| 官方来源与类别 | 实际取得内容、日期与限制 | 与仓库缺口的关系 |
| --- | --- | --- |
| [小红书22021：2027校招AI应用研发工程师-社区工程](https://job.xiaohongshu.com/campus/position/22021) | 官方域名搜索索引含职责与资格：对话/上下文、Tool/RAG、交互、评测与Badcase；直接打开无正文；发布日期未知，非完整实时详情核验 | 已有Agent与SSE，但当前真实Ask/引用/报告链路尚未复跑；采纳效果与失败闭环优先 |
| [小红书22019：2027校招Product Engineer-社区内容](https://job.xiaohongshu.com/campus/position/22019) | 官网索引含2027届本科以上、前端/客户端/服务端任一经验、全栈加分、计算机基础与排障；直开零行，发布日期未知 | Python+Next已有；把故障定位、交付与实际效果讲清楚，比新增技术栈更直接 |
| [小红书2027职位索引：AI全栈企业智能](https://job.xiaohongshu.com/campus/position?positionName=27) | 官方列表索引有Agent落地与稳定性职责，缺独立详情资格，发布日期未知；第三条仅线索 | 不据此新增高并发/多租户范围，保持当前规模 |
| [百度J100679详情](https://talent.baidu.com/jobs/detail/GRADUATE/66a12645-f0f1-435c-8426-9fb91f1be330)、[360校园职位详情](https://360campus.zhiye.com/campus/detail?jobAdId=ee3845e9-d55c-4aec-8302-99854c955e70) | 百度仅官网索引可定位旧岗位，详情超时；360索引有AI Coding流程线索，直开零行，届别/发布日期本轮未核实；不计新增完整样本 | 未取得足够跨企业新证据，不根据标题或第三方转载更改方向 |

开源核验一个项目：[Langfuse Python SDK固定提交](https://github.com/langfuse/langfuse-python/blob/ab861f1f7094acfcdda8d61368a0d66a32cb7062/langfuse/experiment.py)，SHA `ab861f1f7094acfcdda8d61368a0d66a32cb7062`（本轮gh读取main并通过contents API解码该固定文件；提交发布日期未核实，不称最新发布版）。具体参考`ExperimentResult`、`RunnerContext`、`_run_evaluator`：结果/运行元数据独立组织，评测错误是否抛出有明确选项，默认并发50。本项目可借鉴运行回执和错误显式化；其默认并发及捕获错误返回空评分的语义不适合本阶段串行、失败停止的调用边界，不引入SDK、云账号或新增遥测服务。参考[官方数据集说明](https://langfuse.com/docs/evaluation/experiments/datasets)将输入/期望与实验结果分开；这支持后续构建可复核样例，但不能替代当前真实链路验证。

**结论：继续原阶段ENG-05B/ENG-06，不启动新阶段。** 新证据强化端到端效果、评测和排障的重要性，没有改变优先级的充分理由。当前缺口是共享上下文尚未覆盖总运行器、数据使用条件未解决、真实调用清单和预算未确认，继续补闭环；不重复容器/CI阶段，也不为岗位名新增框架。

本周阶段目标与候选交付：先完成适配器业务失败停止（周一已验收），再接受控启动器、抽取/seed/API统一额度与回执；离线验收须证明启动probe计数不漏、跨请求不重置、失败无后续出站、结束可汇总本次run。数据条件、有效模型/token/费用清单齐备后集中确认真实运行；获得授权与可用隔离服务后，再验收五轮Ask引用、报告替换与跨平台浏览器。本周候选并非无条件工期承诺；真实调用/数据条件/服务环境为依赖。来源条件不明确时不先导入正文，继续不依赖数据的工具实现。

### 2026-10-26：聊天与向量响应失败锁定共享运行

- 目标/原因：HTTP200和完整usage只证明请求成功返回；空答案、坏工具参数、错误向量仍可能导致业务重试继续消耗。验收包装器把聊天/向量化解析异常及取消同步给共享guard；首个失败后，后续抽取/聊天/向量化出站都受同一停止标志约束。通用Embedder新增索引必须完整且唯一、值必须有限，阻止正文与向量错配及NaN/Infinity污染，正常乱序仍排序还原。生产聊天仍沿用恢复逻辑；事实错误、工具schema、引用和报告落库失败不在今天断言范围。
- 基线与保护：main起点`f7c0a7ac962150e12f794a9205dd853ebedcd00e`，gh核对远端一致；未发现根/父AGENTS，本次不改前端；可见同仓库其他聊天无活跃开发。原8组未跟踪材料（含output）保留，不读取/暂存其正文。补核昨日最终Backend40178791879、Frontend40178791896、Container40178791884均completed/success，属于昨天CI。
- 实际验证：Windows Python3.12.7、常规进程中执行`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_acceptance_runtime.py tests/test_embedder.py tests/test_acceptance_api_resources.py`，28 passed/2既有warnings，11.14s；完整`.venv/Scripts/python.exe scripts/run_backend_tests.py`为**328 passed/1 POSIX skipped/3既有warnings，17.31s，退出0**。全仓`.venv/Scripts/python.exe -m ruff check backend pipelines shared scripts tests conftest.py ops`通过。新增9个真实SDK+MockTransport回归：聊天空白/空choices/坏工具JSON/取消；向量维度/数量/重复索引/NaN/取消。65输入首批64失败只产生1次wire，第65条、跨适配器调用及调用者重试均无新增wire。既有正常回答、批量与乱序恢复回归保持通过。
- 环境限制：沙箱首次专项无输出，主动中断退出1，不计通过；常规进程专项及完整runner通过。初次只读GitHub访问网络失败，常规只读查询成功；未更改网络/代理/凭据。未发真实模型请求、读取/导入评论、启动数据库/Milvus或复跑前端/容器/wheel/浏览器，不把离线用例当真实业务或语义准确率。
- 可演示能力：无需凭据模拟provider返回HTTP200坏向量或空答案，观察只有首次底层请求、后续均被阻断。代码入口`shared/acceptance/runtime.py`、`pipelines/embedding/embedder.py`、`tests/test_acceptance_runtime.py`；运行说明更新verification，README入口不变不改，无新daily/ADR/历史表同步。
- 剩余与下一步：优先统一受控启动器和抽取/seed/API完整运行上下文，补报告持久化/引用等下游业务失败停止及回执汇总；96次仍只是拟定全流程上界，无人民币硬上限。公开评论条件和真实调用授权未解决，无需重选已确认阶段。
- 实现及verification提交`64f5ecd7be01a09402530515f61be28e91356c21`，4个具体路径，已普通推送origin/main（无强推）。Ruff、git diff/check与暂存检查通过，3 Markdown/17本地链接及行尾检查通过；收尾仅plan/journal，自身SHA由Git/memory/最终回复交接。未将用户材料、运行产物或密钥混入；新CI最终结果尚未核验，不预填成功。

### 2026-10-27：SSE业务失败停止与后台任务清理

- 目标/原因：模型HTTP200、usage和解析通过后，周报结构/引用边界校验、保存或提交仍可能失败。原API把错误转成SSE后没有通知运行guard，下一项验收仍可消费额度。今天在Ask与报告流边界连接共享停止；错误事件yield前已锁定，取消/初始断连/未到终态关闭生成器也锁定。Ask关闭时取消并等待后台turn和队列任务，未完成流关闭时尝试回滚；正常成功和Ask无数据拒答不误停。生产未注入适配器时停止函数为空操作，任务清理仍生效。
- 基线与保护：main起点`667c85bffa0cb2b4bdd11038aaf552555aa0582d`，常规只读gh核对远端一致；根/父AGENTS不存在，本次不改frontend；可见同仓库其他聊天无活跃开发。原8组未跟踪材料保留，无正文读取或暂存。补核起点Backend40278720732、Frontend40278720720、Container40278720803全部completed/success，是昨日CI，不是今天复跑。今天周二无例行JD/开源研究，阶段继续ENG-05B/ENG-06，无新阶段访谈。
- 实际改动：`core/model_resources.py::stop_acceptance_run`只操作显式注入的guard；`api/ask.py`处理ERROR结果/业务异常/提交异常与取消，并清理两类异步任务；`api/reports.py`处理候选校验/保存/提交失败及流关闭。终态先完成序列化再标记成功，读到done/report_completed立即aclose仍可继续下一项。报告若已commit但终态未送出便关闭，停止运行但rollback不能撤销已提交数据，需靠精确回执和数据库审计判断，不能当成未落库。
- 验证环境/命令：Windows Python3.12.7，常规进程运行`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_ask_api.py tests/test_report_generation.py tests/test_acceptance_api_resources.py`，**50 passed/3既有warnings，8.89s**。最终完整`.venv/Scripts/python.exe scripts/run_backend_tests.py`为**341 passed/1 POSIX skipped/3既有warnings，20.16s，退出0**；`.venv/Scripts/python.exe -m ruff check backend pipelines shared scripts tests conftest.py ops`及git diff/check、暂存检查通过。新增13参数场景证明首次wire后业务失败，后续embedding无新wire；成功/拒答允许下一次聊天；取消/aclose后后台turn退出。报告走真实生成服务/Pydantic候选校验，真实SDK+MockTransport，统计/检索/存储/事务为替身；Ask服务为替身但实际调用共享SDK适配器。
- 排障与未验证：沙箱专项无有效统计被中断退出1，不计通过；常规首轮49通过/1失败，发现新终态标志与asyncio.wait返回变量重名造成关闭流漏停，改为terminal_emitted后通过，完整回归包含终态后立即关闭反例。Ruff初轮自动修正2项导入顺序。未发真实模型请求、读取/导入评论、连接真实数据库/Milvus，未复跑浏览器、前端、容器或wheel；不将替身rollback称为真实事务/旧报告保留证明。
- 交付与演示：实现和verification提交`aa545af888b4a7f1f6cadf3a38148d25fa8cade8`，仅6个具体路径，已普通推送origin/main；可无凭据演示模型返回后候选无效/提交失败只产生首次底层请求，下一embedding被挡。plan更新最新结果/边界；README运行与演示入口未变不改；无新daily/ADR/历史表同步。收尾文档提交自身SHA和最终远端/CI状态由Git/memory/本聊天交接，不预填通过。
- 剩余与下一步：受控启动器与抽取/seed/API总运行器、回执汇总仍优先；引用审计失败、服务内恢复后返回成功、流创建前鉴权/schema拒绝尚未统一停止。96次为拟定上界，尚无全流程强制约束或人民币硬上限。数据使用条件/有效模型与token费用清单/真实运行授权仍是依赖，无需用户重新选择阶段。真实业务E2E与在线演示未完成。

### 2026-10-28：单进程阶段编排、seed接线与运行回执

- 目标/原因：独立脚本各建适配器会重置请求计数；只有模型/HTTP成功也不能证明精确回执和落库审计通过。新增`shared/acceptance/workflow.py`持有整轮上下文：prepare → seed → repeat_seed → API启动/启动probe → exercise → 回执校验/audit → API/SDK关闭。整轮仅在正常关闭后完成；阶段异常、取消、已停止却被回调吞错都阻止下一阶段。`RunRecord`保存run UUID、状态、固定阶段/耗时及次数/token汇总，不存回调输出或错误正文；不能复用record，额度高于拟定72/24在调用前拒绝。回执要求本次run、五轮Ask、同范围两次报告及递增时间，随后才允许真实审计回调执行。
- 基线与保护：main起点`0d79185298987015b6c94559e95f9f70b975a4d6`，gh只读核实远端一致；根/父AGENTS未发现，本次未改frontend；可见同仓库其他聊天未活跃开发。原8组未跟踪材料保留，无正文读取/暂存。周三无例行JD研究，阶段与边界不变。补核昨天最终Backend40459857625、Frontend40459857434、Container40459857423均completed/success，属于昨日CI。
- seed实际接线：`seed_demo_data(embedder=adapters.embedder)`可借用运行Embedder，不另建客户端；原独立默认不变。测试两次调用真实seed函数，关系会话/Milvus替身、真实SDK+假wire，20条document/mention merge每轮与相同向量UUID可复核，累计embedding2后共享chat仍可调用。此seed仍是10条合成fixture，不是公开数据准备，也未改变跨库非原子写入边界。
- 实际验证：Windows Python3.12.7常规进程`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_acceptance_workflow.py`首批13 passed/2既有warnings，9.48s；补入真实seed回归后执行完整`.venv/Scripts/python.exe scripts/run_backend_tests.py`，**355 passed/1 POSIX skipped/3既有warnings，18.39s，退出0**。新增共14场景：正常总计chat2/embedding3含probe；prepare、两次seed、启动维度、exercise、audit、跨run回执、关闭失败、取消、吞错、跨阶段额度耗尽，以及两次真实seed注入。全仓`.venv/Scripts/python.exe -m ruff check backend pipelines shared scripts tests conftest.py ops`通过，diff/暂存检查通过。首次沙箱专项无有效输出主动中止退出1，不计通过；常规执行取得上述有效结果。
- 可演示与边界：无需凭据展示阶段推进、失败位置/耗时与累计请求，确认坏回执不进入审计、启动probe不漏计、失败不进入下一阶段。编排回调是可信集成代码，必须使用传入app/适配器，不能防止自行另建客户端；exercise不得二次启动lifespan。实际浏览器/HTTP监听、数据库/Milvus、真实模型/数据、费用仍未验证；本机未复跑前端/容器/wheel，未配置凭据或发布。之前阶段已写入的数据不会因停止自动撤销；真实审计仍需逐项核对。
- 实现及运行说明提交`b7f92fd61fe17288cc2d1d618611df88de2b0555`，仅4个具体路径，已普通推送origin/main。plan/journal收尾提交自身SHA由Git/memory/本聊天交接，避免自引用；README运行入口未变不改，无新daily/ADR/历史状态表同步。
- 剩余/下一步：继续监听服务器与Playwright回调对接，让浏览器使用同一已启动app，接实际数据库审计与样本准备；旧Playwright子进程启动器未纳入守卫，96次全流程约束及人民币硬上限尚未完成。数据使用条件、有效模型/token/费用清单和真实调用许可仍未解决，无需用户重选阶段。新CI结果收尾另行只读核查，不预填成功。

## 2026-W43（10-19 至 10-25）

### 周度研究基线（流程迁移，不是新调研）

本周已有研究与交付见 [10-20历史记录](daily/2026-10-20.md)、[10-21历史记录](daily/2026-10-21.md)。10-20核实百度官方岗位及FastAPI/Dify实践；10-21补充其他企业的官网索引线索、FastAPI镜像细节/RAGFlow入口，并保留动态JD正文未取得等限制。没有在本次配置更新中重新调研或声称新增岗位。

由这些证据与代码缺口推动的CI/制品/容器启动阶段已交付。后续建议转向真实业务链路验收；它仍需要阶段interview确定数据/provider/调用边界。下一次常规集中调研为周一2026-10-26，届时说明研究如何改变本周方案；若无足够新证据，明确继续已确认阶段。

### 2026-10-21：上一阶段验收交接

- 已交付：Python与Next镜像、隔离编排、受控测试provider的启动/失败恢复验证；6个实现/修复加1个收尾文档提交已推送main，最终 `e5323ebbeed5b259ff199dcc50ec62b07a7eb083`。完整SHA、命令与两次失败修复保留在 [当日日志](daily/2026-10-21.md)。
- 历史实测：Windows隔离测试255通过/1跳过/3警告；Linux256通过/4警告；前端35与build通过；最终 [后端CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39612589443)、[前端CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39612589292)、[容器CI](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39612589284)成功。这些不是本次文档迁移重新跑的成绩。
- 尚未验收：本机镜像下载后的复跑、真实模型/数据Ask与报告、周期任务执行、Playwright交互、公网部署；测试向量不代表语义效果。

### 2026-10-21：用户确认并授权工作流调整

- 用户选择：能解释主要调用链/取舍并定位常见故障；每天理解10–15分钟；由助手完成开发，用户理解主线。不要求强制编码作业或手动分批prompt，也不希望每日范围过小。
- 已授权规则：每天12:00独立运行；周一集中调研并总结周报，研究结合代码指导方案；每日延续已确认阶段，自主交付实质成果；取消提交数量目标；重要取舍/范围变化等通过有选项、有推荐的interview讨论。
- 文档整理：根README增加主导航；新增plan与本文件；旧三份状态表原位标记历史、不再同步；保留旧daily/模板/技术手册/ADR。兼容旧开发入口，不删除历史或用户材料。
- 验证与配置更新结果：本条末尾追加。仅工作流/文档调整，不表示下一阶段真实调用或发布已确认。

### 2026-10-22：基线复验与下一阶段interview（待答复）

- 实际运行北京时间约11:54开始（最终结束时刻见automation memory），未倒填12:00。今天周四，不重复例行JD/开源研究；沿用迁移周研究，下一常规研究为10-26。
- 读取自动化记忆、适用指引、README、plan/journal、ADR0001与相关实现。父目录/仓库根未发现AGENTS；frontend/AGENTS已读，本轮未改前端源码。可见聊天中除本次运行外未发现同仓库活跃开发；运行前已跟踪源码与暂存区干净，已有未跟踪材料全部保留。
- 原基线本地/远端main均为 `27a9c6f5b1b95f5b458f3e90d3e3128f5bbf7604`。`git ls-remote`在沙箱因Windows MSYS命名对象权限失败，改用常规环境只读 `gh api repos/Dkgo-0323/Voc-Agent/commits/main --jq .sha` 核对；未改SSH或全局网络配置。查询该SHA的Actions： [Backend](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39619487797)、[Frontend](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39619487443)、[Container](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39619487770)均completed/success，是昨日已运行结果，今天只读确认。
- 今日实际验证：Windows/Python3.12.7，常规进程环境执行 `.venv/Scripts/ruff.exe check --no-cache backend pipelines shared scripts tests conftest.py ops` 全通过；`.venv/Scripts/python.exe scripts/run_backend_tests.py` 为255 passed/1 skipped/3 warnings，16.26s，退出0。跳过为POSIX专用用例；警告来自PyMilvus/pkg_resources、environs/Marshmallow、Starlette TestClient。沿用隔离runner，无真实provider请求。Node22.15.0/npm10.9.2已读版本，本轮未重跑前端、wheel、容器或浏览器验收。
- 审查所得：demo为10条人工构造mention，现有核验脚本要求9条达到质量门槛；seed会先写关系库再请求embedding，不能将中途失败算准备成功。旧trace校验按首问寻找历史会话，不能直接当本次精确会话审计；Playwright仍固定Windows解释器。现有SDK重试、Agent最多3次工具尝试与轮数限制不是总请求/费用硬上限。周报没有持久化mention关联，继续保留无引用卡片边界。以上为代码审查结论，未在真实服务复现。
- 实际改动仅plan与本文件：澄清Phase13/14历史验收和新容器验收的区别，形成隔离数据、数量/检索、追问/拒答、失败、报告替换、跨平台浏览器的验收矩阵、入口、依赖及约2–3日估算。未修改业务代码或新增daily/ADR，不把提案当已确认阶段。
- 已按用户工作流在本次聊天集中提出三题，解释场景/选项/推荐与代价：阶段终点、合成或公开真实数据、先工具清单或有硬上限的真实调用。尚未收到明确选择；沉默不构成授权。待选择的工作暂停，独立的基线核对、离线验证和方案整理已完成。
- 当前可演示能力沿用既有容器启动/失败恢复；今天新增可审阅验收方案，无新的业务演示验收。未执行真实模型/数据抓取/调度任务/浏览器/公网；未读取或修改凭据、未操作旧Docker容器和卷。下一步收到三项选择后更新确认状态，在相同阶段内连续实现，不每日重选。
- 文档验证：本次两份Markdown的12个本地链接、行尾/末尾换行检查通过，`git diff --check`通过；暂存区原为空。交付仅限这两个具体路径，按验证后提交、普通推送main的规则执行；本文自身完整SHA与最终推送结果由git记录、automation memory及最终回复提供，避免提交SHA自引用，不预填尚未执行的结果。

### 2026-10-22：阶段1A/2B/3A确认，验收工具与请求边界交付

- 用户在本聊天明确选择：完整Ask/引用/周报后接浏览器E2E；增加少量公开真实评论，先确认来源/使用范围；先工具和调用清单、不发真实请求。随后明确选择继续核验Amazon Reviews 2023，先限本地最多30篇、优先DELTA 2/Explorer 1000，正文不进Git或公网。当前阶段已确认，不再沿用早间“待阶段答复”状态；真实调用/付费/凭据配置/发布仍未授权。总阶段估计约3–5开发日，数据使用条件和环境排障可能延长。
- 实现并普通推送 `89789826e290d359b826ca0df5ca3b87806adf78`（19个具体路径）：离线规划器、共享回执/报告审计、请求守卫；跨平台无shell API启动器（空cwd避开.env）、显式live opt-in/独立数据库及collection检查；Ask五轮保存精确session/message回执，周报等待本次终态并记录ID/时间/内容哈希；两个CLI只读核对实际指定会话或最终报告。修复历史会话可能混入验收、旧“报告已生成”提示可能误通过的工程缺口；服务产品/数据库schema未变。
- 请求守卫仅是可测试组件，尚未接入API/抽取器；限制明确provider/模型、出站次数、并发、字节大小/输出token参数与1024维/64文本批量，异常/缺usage/失败后停止。假HTTP传输配合真实SDK验证重试不增加出站调用，摘要不含header/prompt/响应正文。它不是人民币预算硬上限；96为拟定清单上界，现有抽取器重试/fallback不满足该假设，有效模型/token/预算与实际runner接线仍未完成。
- 本机实测Windows/Python3.12.7/Node22.15.0：Ruff全仓（含ops）通过；最终 `.venv/Scripts/python.exe scripts/run_backend_tests.py` 为306 passed/1 skipped/3 warnings，15.51s、退出0（较基线增加51用例，POSIX用例仍跳过）。前端 `npm run lint`、`npm run typecheck`通过，完整 `npm test`为9文件54测试通过；最后哈希/数据库query拒绝变更后的专项19通过。后端最终专项transport/report24通过；CLI --help均成功，planner实际输出72 chat/24 embedding、费用null、未授权/未接线。所有请求均为假传输/替身，不是实际provider/数据库集成。
- 验证过程中曾有Ruff格式/导入问题，修复后通过。第一次代码提交前 `git diff --cached --check` 报新增receipt.ts末尾多余空行，但PowerShell命令串未立即退出，代码提交仍发生；已修正末尾空行并在收尾命令加非零立即停止，补交正常新提交，不改写已推送历史。运行逻辑未受该空行影响；不能把首次暂存检查写成通过。
- 真实数据准备尚未开始：只读已有产品metadata的两条匹配记录，无评论正文读取/新增下载/导入。Jackery映射为Explorer1000/1002Wh，EcoFlow为DELTA2/1024Wh带两块220W太阳能板套装，后续保留套装标识并检查问题归属。本地缓存版本未与发布者独立核对，记录指纹不当作官方校验和。
- 一手来源与访问日期2026-10-22、固定数据仓库版本、两条metadata指纹、官方价格依据均记录在verification。许可讨论中发布者明确研究用途但不能授予许可，对他人论文使用表示无异议不能外推本项目；用户已选择继续核验，使用条件仍未解决。未联系发布者/发外部消息。现有合成10条/9合格只作回归，不代替用户选择的真实数据，也不将真实时间改成202403。
- README按E2E入口变化更新；plan回填确认和阶段进度；verification维护真实命令/边界；旧三表、daily、历史ADR和用户材料保留，无新daily或状态表。早间文档提交 `62dcbb3eba2f0fc02f37494c90c4adb689965ce1` 三项CI已核实success，替换早间快照中的进行中状态。
- 未验证：新跨平台启动器实际启动、Windows/Linux浏览器、真实provider/真实样本Ask与报告、真实Milvus证据核验、调用成本、本机容器下载复跑、worker任务与公网。可演示新增能力为无凭据的调用清单及可重复的离线反例审计，不称已有真实业务效果。后续继续使用条件/样本来源完整性核验与预算/runner接线，准备完整清单后才集中确认真实运行；当前无需用户重复确认阶段。
- 实现SHA `89789826e290d359b826ca0df5ca3b87806adf78`三项CI均completed/success：[Backend](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39722565442)、[Frontend](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39722565505)、[Container](https://github.com/Dkgo-0323/Voc-Agent/actions/runs/39722565560)。读取实际job日志：Linux307 passed/4 warnings/13.84s，wheel内容及6个安装导入通过；前端54与生产编译成功；容器正常启动/重复seed/内部网络/可选worker初始化停止/768维拒绝/init失败阻断与恢复全部PASS。容器provider仍为测试向量，无真实任务或模型调用，不代表新E2E启动器已实际运行。
- 收尾检查：4份Markdown共23个本地目标/行尾通过，修正receipt.ts末尾空行后工作区与暂存diff检查通过；仅plan/journal/该空行修正进入收尾提交，用户未跟踪材料不暂存。源码提交已普通推送；收尾提交自身SHA与推送/最终CI状态由git、memory与最终回复提供，不预填。

### 2026-10-22：每日时间、模型强度与复盘详细度调整

- 用户明确要求：每日改为北京时间14:00，模型GPT-6.1 sol、推理强度中，每天复盘和解释更详细。
- 已通过现有automation接口更新同一任务`voc-agent`，返回ACTIVE；读回配置确认14:00、`gpt-6.1-sol`、`medium`及新复盘要求全部保存。任务ID/名称/项目/本地独立运行/创建时间均与修改前一致，没有新建重复任务。
- 复盘要求已展开为具体场景、核心调用链及输入输出、概念与技术取舍、实际验证证据、1–2个相关故障定位例子、阶段进度/下一步，并提供2–4个必要代码入口；仍按约10–15分钟理解，不要求逐文件阅读或强制编码。周一研究、阶段自主推进和真实调用/数据/发布授权边界保留。
- 同步plan当前规则，保留此前12:00的历史记录。仅配置与两份工作流文档变更，无业务代码/真实模型/部署，本次无需业务测试；配置逐字段读回通过，文档diff与提交结果由git/memory记录，最终提交自身SHA由memory与本聊天交接提供。

### 2026-10-23：运行级请求守卫与业务适配器接线

- 延续已确认阶段，无新架构/数据/模型调用决策。起点main `22dc5c1cda021a4920af6361478714afd8c0998f`，保留其他聊天新增的中文README、截图与技术指南；只读GitHub核对远端一致，可见其他同仓库聊天空闲。原有7组未跟踪用户材料不暂存。
- 新增shared/acceptance/runtime.py：由调用者显式传入策略、密钥与HTTP transport，单次运行上下文向聊天模型/Embedder注入同一SDK客户端与守卫，零SDK重试、关闭重定向/环境代理，固定1024维和64条批次；统一关闭HTTP资源。没有默认网络transport，不自动从生产API启用。Embedder模块仍导入应用settings，后续运行器须沿用空cwd/隔离环境，不能宣称模块导入完全不加载配置。
- 两个业务集成回归使用真实OpenAI SDK、真实聊天/Embedder适配器与MockTransport：65条输入拆为64+1批，聊天1次/嵌入2次共用计数，汇总prompt6/completion3；嵌入429后，随后聊天也失败且底层仅收到1次请求。摘要不含测试问题正文。没有真实网络、模型或数据库。
- Windows既有Python3.12环境：`.venv/Scripts/python.exe scripts/run_backend_tests.py`常规进程308 passed/1 POSIX skipped/3既有warnings，17.20s、退出0；`.venv/Scripts/python.exe -m ruff check backend pipelines shared scripts tests conftest.py ops`通过；git diff --check通过。初次沙箱专项pytest无输出，主动中止退出1，不计通过；Ruff初次3项导入格式问题自动修复后通过。
- 可演示能力：无凭据的离线业务适配器成功/故障回归。未跑前端、浏览器、Docker、真实provider/数据/成本；无前端和运行入口变化，README与技术运行手册不改。真实数据使用条件仍未解决，本轮未重复调研/读取评论正文。
- 阶段剩余：启动探测、API依赖、抽取器重试/fallback与跨进程全局额度尚未接到此上下文；本次只证明业务适配器接线，不代表完整运行器、人民币上限或96次全流程约束。下一步继续完整运行器与隔离目标接线，核验数据条件；清单完备后集中确认真实调用。
- 实现提交 `3cb5077edcb625bcca758c8b7d8a0122e39b34a7` 已普通推送origin/main，gh只读核对远端SHA一致，仅4个具体路径。该条推送证据另以收尾文档提交保存，其自身SHA见Git/memory与最终回复；未查询本次新CI，不预填成功。

### 2026-10-24：抽取链路零重试与业务失败停止接线

- 延续已确认的ENG-05B/ENG-06阶段，周六不重复例行JD/开源研究。起点main `e988b5096d1b28be3aa0be4c4ca51f51245cfbdc`，只读gh核对远端一致；根/父目录无AGENTS，未改frontend，当前可见同仓库其他聊天无活跃开发。原有7组未跟踪材料保留。补核昨日该SHA的Backend39909239296、Frontend39909239305、Container39909239325全部completed/success，属于历史运行而非今天重新验收。
- 场景：模型HTTP 200但返回缺失文档ID或虚构引文时，HTTP守卫无法自行识别业务失败；原抽取器还会重试/单篇fallback，不能直接用于零重试验收清单。新增AspectExtractor显式fail_fast选项，默认false保留生产恢复行为；验收工厂提供同一SDK/模型/token策略下的extractor，设为true关闭重试/fallback。验收包装器将协议异常、文档级失败、输入异常与取消传播到同一guard.stop()停止标志，之后其他适配器或调用者重试均不能新增出站请求；不把错误正文存入摘要。正常空aspects及请求前噪音过滤逻辑保留，未修改产品schema或证据校验规则。
- Windows/Python3.12.7常规进程环境，隔离runner清理应用环境并使用空cwd：`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_acceptance_runtime.py tests/test_aspect_extractor.py`最终23 passed/2既有warnings，8.61s；完整`.venv/Scripts/python.exe scripts/run_backend_tests.py`为314 passed/1 POSIX skipped/3既有warnings，18.41s。`.venv/Scripts/python.exe -m ruff check backend pipelines shared scripts tests conftest.py ops`及git diff/check、暂存diff/check通过。首轮新fixture漏填7个必填字段导致6 failed/17 passed，补齐None字段后重跑通过；首次Ruff修正1处导入排序。未弱化业务断言。
- 六个新增用例用真实OpenAI SDK+MockTransport：成功抽取与聊天共享chat额度/明确模型和max_tokens；429、错误JSON、缺ID、虚构引文和取消各仅1次底层请求，之后embedding与再次抽取均被阻断。既有生产重试/单篇fallback回归通过。没有真实网络、评论、数据库或服务；这是离线业务适配器验收，不证明语义质量/真实效果，也未将人民币金额或96次全流程上限标记为已生效。
- 实现及运行手册提交 `4f836c579c0ea5217677b582dbdc0954a840640b`（5个具体文件）已普通推送origin/main，无强推；plan与本条交接另作收尾提交，自身SHA由Git/memory/最终回复提供。README入口未变不改，无新daily/ADR，不同步历史三表；无用户材料、凭据或运行产物进入暂存区。
- 当前可演示：无需凭据的抽取失败停止及共享额度离线反例。未重跑前端/浏览器/容器/wheel，未启动真实API/调用模型/导入评论/操作旧数据卷，未预填本次新CI成功。真实评论使用条件仍未解决，本轮未重复访问来源或读取正文；真实调用尚未授权，无需重新阶段访谈。
- 阶段剩余：API启动维度探测、Ask/周报依赖及跨进程总运行器仍可能创建独立客户端，需要在下一增量统一运行上下文并离线验证无旁路；embedding/聊天响应的其他业务语义失败停止范围也尚未统一。之后核实有效模型、输入输出token/费用清单与数据条件，再集中确认真实运行。今天不将抽取器接线当作完整运行器完成。

### 2026-10-25：API启动、Ask与周报共享验收上下文

- 本轮实际在北京时间16时段执行（未倒填14:00）；延续已确认ENG-05B/ENG-06阶段，周日不重复例行调研，无新阶段/架构/调用决策。读取memory、根README、plan、当前周journal、ADR0001和真实代码；根及父目录无AGENTS，本次未改frontend。main起点`e1c110cd0137b57dc1078c743c3b1ecee01d63fa`，只读gh核对远端一致，可见同仓库其他聊天无活跃开发，原7组未跟踪材料保留。补核起点Backend40068911339、Frontend40068911346、Container40068911365均completed/success，属于昨日CI。
- 目标/原因：即使抽取器共享守卫，原API启动探测、Ask和周报各自构造模型客户端仍可绕过验收总额度。新增`create_app(acceptance_adapters=...)`显式Python注入；启动维度探测和两类请求借用外层运行上下文的chat/embedder，共享计数、策略和停止标志。请求退出不关闭共享客户端，外层上下文负责资源。普通uvicorn入口不自动启用守卫；生产两类请求的客户端创建/关闭合并至`core/model_resources.py`，保留原配置/提供商选择。启动失败或取消锁定guard并释放DB，运行体异常也通过finally释放DB；注入时日志使用实际策略模型及1024维。
- 验收：Windows Python3.12.7，常规进程下`.venv/Scripts/python.exe scripts/run_backend_tests.py`使用既有空cwd/清理应用环境runner，完整**319 passed / 1 POSIX skipped / 3既有warnings，48.31s，退出0**。`.venv/Scripts/python.exe -m ruff check backend pipelines shared scripts tests conftest.py ops`通过；git diff --check及暂存检查通过。新增5个回归用例，真实FastAPI lifespan/依赖解析、真实OpenAI SDK+MockTransport，数据库/SKU/Milvus初始化为替身。诊断路由只在测试中存在，不是产品新增API：启动embedding1次、Ask chat1次、周报embedding1次/chat1次，共4次底层请求；下一次Ask额度耗尽且底层请求数不变，禁止额外SDK构造。429/768维/取消均启动拒绝、DB关闭、后续聊天无法出站；运行体异常关闭DB。
- 排障记录：最初专项命令误写不存在的`tests/test_reports_api.py`，未执行测试；移除错误路径。两次专项无输出被主动中断退出1，均不计通过；25秒faulthandler诊断在收集阶段的pymilvus→minio模块读取处超时，不是断言失败或已证明死锁。完整runner随后正常完成。初次Ruff修正导入排序，测试诊断路由改用Annotated依赖并将宽泛异常断言收紧为具体异常；429在守卫层转换为SDK APIConnectionError，修正对应预期，未弱化底层次数/停止断言。
- 可演示成果：无凭据离线展示启动与跨HTTP请求共用额度，以及启动失败关闭后续出站。未启动真实API/数据库/Milvus、调用真实模型、读取/导入评论、复跑浏览器/前端/容器/wheel；不将5个接线测试称为真实Ask业务端点、报告生成/落库或语义质量验收。真实评论使用条件仍未解决，未重复读取正文或访问来源；无需用户重选阶段。
- 实现及运行说明提交`efa9618d8ea0024b32d918071d6a0af070b405ff`，仅6个具体路径，已普通推送origin/main并通过gh只读核对远端SHA一致。plan仅更新接线状态与下一步；README运行/演示入口未变，不改；无新daily/ADR/旧状态表同步。原材料、密钥与运行产物不暂存。
- 推送后只读CI快照：实现提交Backend40178730938、Frontend40178730879、Container40178730925均in_progress，不预填成功。收尾plan/journal文档提交自身SHA由Git/memory/最终回复交接。3份Markdown共17个本地链接/行尾检查通过。
- 剩余/下一步：当前只统一单进程API上下文；现有Playwright启动器尚未使用此工厂，抽取/seed/API跨进程总运行器与96次全流程约束未完成，人民币硬上限未实现。聊天/向量化及报告的其他业务校验失败停止仍需补齐。继续受控启动器与整体额度/回执汇总接线，核实来源条件和模型/token/费用清单后再集中确认真实运行；真实调用、凭据、付费和正式发布均未授权。

## 后续追加约定

每周一在相应周标题下写一份简明周报：直接证据与可信边界、对仓库缺口的判断、是否调整优先级、周目标/候选交付/依赖/验收。其余日子不重复例行研究，只按实现问题查必要资料。

每次有意义增量完成、暂停或受阻时，在当周日期下简记：为什么做、实际改动、验证命令/环境/结果与未验证项、完整SHA/推送、可演示成果、阻碍与下一步。跨天任务延续原记录；新决策记用户选择与理由，重要架构再链接ADR。不要预填通过或完成，不复制所有计划/全部原始日志。

每天面向用户的主线说明覆盖：问题和价值、核心请求/数据链路及变化、真实验收/限制、阶段进度和下一步；适合10–15分钟理解，以具体场景和少量代码入口解释概念。需要决策时先解释再提2–4题，每题2–3个选项与推荐理由/代价。学习说明本身不阻断已授权常规推进。

### 本次工作流迁移的验证与交付

- 2026-10-21约22:38，通过现有automation更新接口修改任务voc-agent，返回ACTIVE；未新建重复任务。读回automation.toml核实新提示词保存成功；每天北京时间12:00、项目、独立cron运行、本地环境、原模型与推理设置保留。
- 15份Markdown本地链接/交付文档已跟踪目标/行尾检查通过；git diff --check通过。逐份比较旧status/roadmap/backlog，除停用提示外原文完全保留；旧daily/ADR没有改写。
- 本次只有工作流配置与文档迁移，未改业务源码、未重跑业务测试或部署，也未把上一阶段测试成绩写成本次重跑。下一阶段真实业务目标仍待必要interview，不把本次流程授权扩大为真实调用/付费/凭据/发布授权。
- 文档只按本次7个具体路径提交、普通推送现有main；自身完整SHA与最终推送结果由git log、自动化memory及本聊天最终说明提供，避免自引用。后续日更从本文件续写，不再生成daily独立文件或同步旧状态表。
