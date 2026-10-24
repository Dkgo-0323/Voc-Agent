# VOC Agent 开发记录

按北京时间、ISO周组织周报与日更；当前目标/优先级只维护 [plan](plan.md)，运行入口见 [根README](../../README.md)。保留已确认决定和真实交付，不复制三份状态表。

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

## 后续追加约定

每周一在相应周标题下写一份简明周报：直接证据与可信边界、对仓库缺口的判断、是否调整优先级、周目标/候选交付/依赖/验收。其余日子不重复例行研究，只按实现问题查必要资料。

每次有意义增量完成、暂停或受阻时，在当周日期下简记：为什么做、实际改动、验证命令/环境/结果与未验证项、完整SHA/推送、可演示成果、阻碍与下一步。跨天任务延续原记录；新决策记用户选择与理由，重要架构再链接ADR。不要预填通过或完成，不复制所有计划/全部原始日志。

每天面向用户的主线说明覆盖：问题和价值、核心请求/数据链路及变化、真实验收/限制、阶段进度和下一步；适合10–15分钟理解，以具体场景和少量代码入口解释概念。需要决策时先解释再提2–4题，每题2–3个选项与推荐理由/代价。学习说明本身不阻断已授权常规推进。

### 本次工作流迁移的验证与交付

- 2026-10-21约22:38，通过现有automation更新接口修改任务voc-agent，返回ACTIVE；未新建重复任务。读回automation.toml核实新提示词保存成功；每天北京时间12:00、项目、独立cron运行、本地环境、原模型与推理设置保留。
- 15份Markdown本地链接/交付文档已跟踪目标/行尾检查通过；git diff --check通过。逐份比较旧status/roadmap/backlog，除停用提示外原文完全保留；旧daily/ADR没有改写。
- 本次只有工作流配置与文档迁移，未改业务源码、未重跑业务测试或部署，也未把上一阶段测试成绩写成本次重跑。下一阶段真实业务目标仍待必要interview，不把本次流程授权扩大为真实调用/付费/凭据/发布授权。
- 文档只按本次7个具体路径提交、普通推送现有main；自身完整SHA与最终推送结果由git log、自动化memory及本聊天最终说明提供，避免自引用。后续日更从本文件续写，不再生成daily独立文件或同步旧状态表。
