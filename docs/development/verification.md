# 交付验证入口

适用版本：方案 A（2026-10-20），Python 3.12 / Node 22。对应工作流为 `.github/workflows/backend-ci.yml` 和 `frontend-ci.yml`。这两个门禁不部署服务，也不要求模型凭据。

## 普通本地检查

在仓库根目录安装锁定依赖并检查后端：

```powershell
uv sync --locked --extra dev
uv run --no-sync ruff check backend pipelines shared scripts tests conftest.py
uv run --no-sync python scripts/run_backend_tests.py
```

`run_backend_tests.py` 在空工作目录运行 pytest，使用仓库配置和测试路径，只传递必要 OS 环境变量并显式指定源码路径。它不读取开发者 `.env`、不继承应用密钥或 APP_ENV 等业务配置。因此默认配置测试不会被本机 provider 地址污染；既有依赖替身负责隔离 PostgreSQL、Milvus、模型调用。它不是外部服务集成测试，也不是 OS 级网络沙箱。

只运行一个文件或排查输出捕获问题：

```powershell
uv run --no-sync python scripts/run_backend_tests.py tests/test_embedder.py
uv run --no-sync python scripts/run_backend_tests.py --capture=sys
```

`--capture=sys` 仅是诊断选项，不降低断言或跳过测试。直接从仓库根目录运行 `pytest` 仍可读取当地 `.env` / 环境变量；CI 与常规离线检查优先使用隔离入口。不要为了跑单测配置真实模型密钥。

前端在 `frontend/` 目录执行：

```powershell
npm ci
npm run lint
npm run typecheck
npm test
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
$env:NEXT_TELEMETRY_DISABLED = "1"
npm run build
```

`typecheck` 先运行 `next typegen`，生成干净检出中尚不存在的 `next-env.d.ts` 和路由类型，再执行 TypeScript。`NEXT_PUBLIC_API_BASE_URL` 是构建时公开配置，不能填写容器内部主机名或密钥；上述回环地址仅用于验证构建，不代表已部署或有 API 正在监听。生产构建继续使用 Next.js 默认 Turbopack。

## Python 制品检查

源码目录可导入不等于 wheel 可用：editable 安装和 PYTHONPATH 可能掩盖缺包。因此单独建立安装环境，先锁定依赖，再安装实际构建的 wheel。以下 PowerShell 命令在**独立终端**、仓库根目录执行，环境位于忽略的 `dist/`，不覆盖原 `.venv`：

```powershell
$env:UV_PROJECT_ENVIRONMENT = "dist/wheel-check-env"
uv sync --locked --extra dev --no-install-project --python 3.12
uv build --wheel --out-dir dist/release
uv pip install --python dist/wheel-check-env/Scripts/python.exe --no-deps --reinstall dist/release/voc_agent-0.1.0-py3-none-any.whl
uv run --no-sync python scripts/check_distribution.py dist/release/voc_agent-0.1.0-py3-none-any.whl --python dist/wheel-check-env/Scripts/python.exe
```

每条命令必须成功后再执行下一条；版本变更时替换 wheel 文件名。`--no-deps` 的前提是上一条锁定依赖安装已成功，不应跳过。`--reinstall` 避免本地重复检查时同版本旧 wheel 被复用。

Linux CI 使用新建 `.venv`，对应安装命令为：

```bash
uv sync --locked --extra dev --no-install-project
uv build --wheel --out-dir dist/release
uv pip install --python .venv/bin/python --no-deps dist/release/*.whl
uv run --no-sync python scripts/check_distribution.py dist/release/*.whl --python .venv/bin/python
```

检查器验证必需模块、迁移脚本/模板及常见本地敏感路径，再用目标解释器 `-I` 在空目录导入 API、worker、seed、ingestion 和评测入口；每个入口必须来自目标环境的 site-packages。子进程禁止网络连接，且不执行 FastAPI lifespan、迁移、seed 函数、worker 调度或 provider 调用。它检查文件名和路径，不是通用内容密钥扫描器，也不证明所有运行逻辑正确。

wheel 包含 `backend`、`pipelines`、`shared`；Hatchling 固定为 1.32.4。测试、原始数据、运行产物和本地 `.env` 不应进入制品。不得将 `dist/`、原始数据或本机配置加入 Git 提交。

## CI 结果与故障定位

- 两个工作流在 main push、面向 main 的 PR 和手工触发时运行；仅具备 `contents: read`，不使用业务 secrets。Python 依赖来自 uv.lock，前端来自 package-lock.json；构建后端、uv 及 Actions SHA 也固定版本。
- 后端包括锁定安装、Ruff、确定性测试、wheel 构建、安装后导入；前端包括 npm ci、lint、类型生成与检查、Vitest、生产 build。任一步失败都会使对应 job 失败，未配置忽略失败。
- 本地安装通过不能证明 Linux runner 通过；远端请按精确提交 SHA 查看 [GitHub Actions](https://github.com/Dkgo-0323/Voc-Agent/actions)。当日实际结果、运行链接和提交见 [daily](daily/2026-10-20.md)。
- Windows 沙箱出现 Turbopack Node 子进程连接失败、uv 缓存 `Access denied` 或 pytest 无输出时，先在正常权限的开发终端对照同一命令并保存结果。2026-10-20 的构建在常规进程环境通过，无需切换构建器；pytest 特定沙箱阻塞根因尚未证明。不能把环境失败改写成测试通过。
- pytest 的默认 provider 配置断言失败时，检查是否人为设置了 EMBEDDING_BASE_URL 等变量；先使用隔离入口，不修改默认值或弱化断言。
- 制品检查若提示缺包，检查 wheel 内容和实际安装来源；若导入来自 checkout，移除验证环境里的 editable 安装并重新安装 wheel。不要通过给烟测添加源码 PYTHONPATH 绕过。
- Linux 的 `.venv/bin/python` 通常是符号链接；调用它时须保留 venv 路径，不能用 Path.resolve() 将其改为系统解释器。本轮首次后端 CI 因该问题失败，已修复，并用真实 POSIX venv 子进程增加回归检查。
- 本轮仍有 PyMilvus/pkg_resources、environs/Marshmallow、Starlette TestClient 的既有弃用警告，以及旧 `tool.uv.dev-dependencies` 配置警告。记录警告，不将其当成失败或顺带升级依赖。

## 需要真实服务的后续检查

普通 CI **没有**验证 Docker 镜像、完整编排、数据库迁移/恢复、真实 provider、Milvus 集合、embedding 1024 维启动探测、Playwright 真实链路或公网部署。

这部分继续沿用 README 的隔离数据库/collection 和 provider 说明。API 必须满足迁移、基础 seed、锁定 SKU、Milvus 与维度契约后才能启动；仅检查 YAML 或单测通过不能替代真实启动。10-22已将Playwright API命令改为跨平台启动器，离线检查见下；实际Linux/Windows浏览器启动仍需真实服务验收。不得将 CI 临时资源清理命令用于用户现有卷或数据库。

10-20 时镜像与编排尚未验证；10-21 新增的容器启动门禁见下节。真实模型调用、凭据配置、付费资源和公网发布按确认范围执行。

## 容器启动与失败恢复（10-21 新增）

操作与边界见 [ops 运行手册](../../ops/README.md)，确认取舍见 [ADR 0001](decisions/0001-container-startup-contract.md)。从仓库根执行：

```sh
python scripts/run_container_smoke.py --build
```

使用独立随机项目与空 env-file，内部测试网络、测试 embedding 服务；覆盖正常启动、重复迁移/seed、1024/768 维契约、init 失败阻断与恢复、登录/空 dashboard/CORS 和前端静态资源。只清理自己新建的项目和卷，不操作根 Compose 或旧数据。完整命令和端口变化后的重建方式在 ops 手册。

该流程进入独立的 [Container delivery workflow](../../.github/workflows/containers-ci.yml)，不需要模型密钥。原普通双端 CI 依旧不启动存储或 provider；容器 CI 的通过也只证明测试依赖下的启动契约，不能代替真实模型、Ask/报告效果、调度任务运行、Playwright 浏览器交互或公网验收。本地 Docker Hub/ECR 下载失败与远端验收分别记录在 [10-21 daily](daily/2026-10-21.md)，不要把远端通过写成本地已能复跑。

## 业务验收工具（10-22新增）

用户已确认阶段目标为Ask、引用、周报和浏览器E2E，并选择增加少量公开真实评论、先确认来源/使用范围、先工具与调用清单。**真实调用尚未授权**；以下离线命令不会启动服务、加载业务.env或请求模型：

```powershell
uv run --no-sync python scripts/plan_business_acceptance.py --documents 30 `
  --chat-model glm-4-flashx-250414 --embedding-model embedding-3
uv run --no-sync python scripts/run_backend_tests.py tests/test_acceptance_tools.py tests/test_acceptance_transport.py tests/test_acceptance_runtime.py tests/test_report_receipts.py
Push-Location frontend
npm test -- --run tests/acceptance-runtime.test.ts
Pop-Location
```

模型参数是拟定标识，不是读取本机配置所得。规划器默认模型为null、费用为null，始终输出`live_authorized=false`和`enforced_by_runtime=false`；没有执行模式。最多30篇，每篇最多3个mention，零SDK/抽取重试，两次seed、一次API启动、五轮Ask、两次周报，拟定请求上界为chat72/embedding24、合计96。它不包括真实judge、worker、抓取或额外启动，实际样本/服务不满足假设时重新规划。旧抽取器有2次重试和单篇回退，不能直接当作符合此清单。

`shared/acceptance/transport.py`提供`AcceptanceTransport`：同一明确HTTPS provider、两个明确模型，串行发送；发出前预占chat/embedding次数，输入字节数/输出token参数/64文本批量/1024维检查，错误、超时、缺usage、次数耗尽后阻断后续请求。用真实OpenAI SDK配合httpx假传输测试重试也不能增加出站请求。它只记次数和provider报告的token用量，不保存header、密钥、prompt或响应正文；**不实现人民币金额硬上限**。

10-23/24新增的`shared/acceptance/runtime.py::acceptance_adapters`要求显式策略、密钥与transport，无默认网络transport；同一上下文提供chat、embedder、extractor及guard，SDK零重试。验收extractor显式使用`AspectExtractor(fail_fast=True)`，关闭抽取重试及单篇fallback；错误JSON/文档ID、文档级校验失败和取消均锁定同一guard，后续聊天、向量化或调用者重试不能新增出站请求。正常空aspects可通过；噪音过滤仍在请求前执行。生产抽取器默认仍有恢复逻辑，不能直接当成验收适配器。HTTP成功只代表收到响应，业务协议是否有效由抽取器另行校验；`stop()`只保留停止标志，不保存错误正文。

复现新增离线反例：`uv run --no-sync python scripts/run_backend_tests.py tests/test_acceptance_runtime.py tests/test_aspect_extractor.py`。真实SDK+MockTransport检查共享聊天额度、429、错误JSON、缺ID、虚构引文与取消，每个失败用例最多一次底层请求，后续embedding及抽取重试均不出站。这里没有数据库、真实评论或真实模型。模块导入仍涉及settings，须沿用空cwd与隔离环境的runner。10-25已增加API工厂的显式上下文注入，见下节；跨进程完整运行器尚未接入，全流程96次上限仍未生效，未来runner还须接入总预算/token/停止控制；不同provider地址也需要相应共享计数设计，不能静默绕过。

### API启动、Ask和周报共享上下文（10-25）

`backend.app.main.create_app(acceptance_adapters=adapters)`是供后续受控运行器使用的Python接线入口。外层`async with acceptance_adapters(...)`必须覆盖应用启动、所有HTTP请求以及应用退出；API只借用chat/embedder，不在单个请求结束时关闭或重建它们。启动维度探测也使用同一个embedder并计入embedding额度。Ask与周报依赖统一通过`backend/app/core/model_resources.py`取得适配器；未注入时，普通`backend.app.main:app`继续使用按请求创建/关闭的生产客户端及现有配置。

此入口不接受HTTP参数或环境开关来创建守卫，也不自动提供凭据或网络transport。调用者仍负责数据来源、隔离数据库/集合、批准的模型策略与运行许可。它解决单进程API内的共享额度；现有Playwright子进程启动器尚未自动使用该工厂，抽取/seed和API跨进程总额度也未统一。不能据此执行真实运行或宣称96次全流程约束完成。

启动的数据库、SKU、Milvus或维度探测失败（包括取消）会锁定注入的guard并关闭DB，不进入接收请求阶段；正常运行体异常退出时也释放DB。启动日志在注入模式使用实际策略的embedding模型/1024维，避免打印生产默认模型造成误判。HTTP/usage/额度失败与既有抽取校验失败可停止后续出站；并非所有Agent/周报业务校验失败都已统一传播到guard。

离线复现：`uv run --no-sync python scripts/run_backend_tests.py tests/test_acceptance_api_resources.py`。用真实FastAPI lifespan/依赖解析、真实SDK和MockTransport，存储初始化替身；诊断路由仅存在于测试中。验证一次启动embedding、Ask聊天、周报embedding与聊天共4次底层请求，下一次Ask额度耗尽而不出站；禁止额外SDK构造，确认请求结束不关闭共享客户端。另覆盖429、768维、取消导致启动拒绝/锁定，以及运行体异常时DB关闭。它不调用真实Ask业务端点或报告持久化，不证明模型语义、真实数据库、Milvus、浏览器或成本。

### 浏览器回执和精确数据库核验

E2E配置和启动器均要求`PHASE14_ALLOW_LIVE=1`、本次UUID `PHASE14_RUN_ID`、本地`voc_phase14`或`voc_acceptance_*`数据库，以及`aspect_mentions_phase14_*`或`voc_acceptance_*`集合。不自动创建、迁移或清理数据库/collection；前缀检查只降低误选风险，不证明资源为空或本次拥有。真实运行需另行确认，设置开关本身不代表工作流已授权。解释器按平台选择，绝对路径覆盖允许含空格；用Node spawn参数数组、`shell:false`执行。API在本次创建的dist临时空目录启动，PYTHONPATH仅指向源码，避免自动读取根.env；模型与认证配置须由已批准的运行器通过环境明确传入。这里只清理自身临时目录。

Ask测试等待本次POST完整SSE，要求唯一成功`done`及三个UUID，拒绝终态后多余data或error；全部五轮通过后才保存`ask-receipt.json`，只含schema/run/session/user/assistant ID。周报测试等待本次`report_completed`，核对SKU/week、重生成保留report ID并更新generated_at，保存只含ID/范围/时间与内容SHA256的`report-receipt.json`。`verify_phase14_report_receipt.py`按同一run ID查询对应SKU/week报告，要求数据库最终ID、时间和正文/摘要哈希与本次回执一致；旧报告、后来被替换的报告或内容不一致都拒绝。哈希采用UTF-8 JSON数组，Python/TypeScript用同一个中文/英文已知向量交叉校验。这修复了仅看旧“Weekly report available”提示可能误通过的问题，尚未实跑浏览器。

根README给出显式运行方式。Ask结果审计必须传`--receipt`和匹配`--run-id`；CLI参数无效时先拒绝，数据库导入/连接延迟到合法输入之后。只查询回执指定会话，检查全部五轮消息ID、顺序、prompt、实际执行工具、追问week、成功/拒答状态与合成fixture引用范围；多余/缺失/历史消息均失败。它仅审计持久化元数据，不证明数值/自然语言正确，也不单独证明Milvus实时provenance；后者仍需数据核验脚本和真实服务。通用审计模块可供后续真实样本适配，当前CLI仍专用于合成Phase14。

Playwright trace可能包含页面、网络、token与评论；只保留在忽略的本地产物路径，分享前单独检查，不提交或自动上传。JSON回执去正文不表示整个Playwright产物已去敏。

### 公开评论来源与范围（路线已确认，使用条件继续核验）

访问日期2026-10-22；这里只核查发布信息，未新增下载/导入评论正文。

| 证据 | 核查结果与限制 |
| --- | --- |
| [McAuley Lab官方发布页](https://amazon-reviews-2023.github.io/main.html) | 覆盖1996年5月至2023年9月；不是2026实时反馈。Patio_Lawn_and_Garden有官方review/meta链接，可配合产品元信息映射；不根据相似产品名代替SKU核对 |
| [发布者数据卡](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e/README.md)、[固定版本文件树](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e) | 固定版本`2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e`；本次所读卡未找到license字段，根列表未见LICENSE；未取得明确可再分发依据，不把数据公开可访问认定为可镜像正文 |
| 仓库`pipelines/config/targets.py`、`pipelines/ingestion/amazon_loader.py` | 已有该来源的解析和ASIN映射，可减少新接入工作；这些映射仍须与选取样本的产品元信息复核，不能将同系列/Pro版本自动视作锁定SKU |

候选范围：最多30篇、优先DELTA 2与Explorer 1000两个mid档SKU；只作本地工程验收，原文和输入文件放忽略的data/dist，去除user_id、作者/图片等不必要字段，不进Git、不用于当前公网展示。保留源版本、产品ASIN、原始日期/ISO周、抽样方法、文本哈希与引用位置；不将真实评论改日期凑到202403，不夸大为代表性市场样本。若明确使用条件不足，继续核验或改用许可明确的来源，正文导入不先行。用户已在本聊天明确确认来源路线A、范围A：继续核验该来源的使用条件与产品映射，仅本地最多30篇；条件明确后才整理样本，目前不导入正文。真实provider处理这些文本仍须另行确认调用。

补充一手证据：[发布者组织账号在许可讨论中的回复](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1)（2024-03-08）明确其主要提供研究用途，并不能为数据授予许可/规定使用条款；2024-12-08对另一用户的非商业论文使用表示无异议。这不是本项目或公开再分发的单独许可；当前不将使用条件标记为已解决，也未联系发布者。

仅对本地已有产品metadata做了只读映射核对（未读取评论正文）：`B0BMQ9FGFS`标题为Explorer 1000/1002Wh；`B0BNL7R3L1`标题为DELTA 2/1024Wh加两块220W太阳能板套装。与当前两个mid档SKU核心容量匹配，但EcoFlow套装评论可能谈配件，后续需保留套装标记、人工核对归属，不能把太阳能板问题自动归为主机缺陷。该缓存文件的发布版本/完整性尚未独立核验；两条metadata原始行SHA256分别为`540b9e9aafcdade318100a731d4241a7d9eea29b46f5f2372c0ccc581ce5921b`与`2dffee597275acc4ec749894ab88868b5684577eecc560f9b81021f445b6d64d`，只作为本地读到的记录指纹，不当作发布者校验和。

### 2026-10-26：HTTP成功后的业务解析失败停止

`shared.acceptance.runtime.acceptance_adapters`的聊天和Embedder包装器现在将解析异常及取消传递给同一个`guard.stop()`；聊天空白且无工具调用、工具ID/名称缺失或参数不是JSON对象也拒绝。生产聊天适配器仍保留原来的解析/恢复行为。通用Embedder除数量/维度外，要求响应索引排序后恰为`0..batch_size-1`，且每个值有限，避免重复向量错配正文或NaN/Infinity流入向量库。正常乱序响应仍恢复输入顺序。

离线复跑：`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_acceptance_runtime.py tests/test_embedder.py tests/test_acceptance_api_resources.py`。Windows Python3.12.7常规进程下28通过/2既有warnings（11.14s）；完整runner328通过/1 POSIX跳过/3既有warnings（17.31s）。真实SDK+MockTransport模拟HTTP200损坏内容和取消，断言首批64条失败后不发送第65条，随后聊天/embedding或调用者重试无新wire。该层不证明答案事实正确、工具参数符合每个工具schema、引用有效或报告成功落库；下游业务失败和跨进程完整运行器仍待接线。未发真实请求或运行浏览器。

### 2026-10-27：SSE业务失败与提前关闭停止运行

显式注入验收适配器时，Ask与报告SSE使用`core/model_resources.py::stop_acceptance_run`锁定同一guard。Ask的ERROR结果、业务异常、提交失败，以及报告候选校验、保存、提交失败，都会在错误事件yield之前停止后续模型出站；取消、初始断连和未到终态就关闭生成器也停止运行。Ask提前关闭时取消并等待后台turn和队列等待任务；未完成的生成器关闭会尝试回滚。普通生产应用没有注入适配器，停止函数为空操作，新增任务清理仍适用。

只有完成提交并构造成功终态后，流才被标记完成；消费端读到`done`/`report_completed`后立即关闭流不会误停下一项验收。Ask的正常无数据拒答`abstained`仍是可接受终态，`partial`沿用原业务状态，不能据此声称事实/引用验收通过。报告若已经提交但终态尚未发出便断流，运行保守停止；后续rollback不能撤销已成功提交的数据，仍须用精确回执/数据库审计判定结果，不能假定失败等于没有写入。

复现：`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_ask_api.py tests/test_report_generation.py tests/test_acceptance_api_resources.py`，Windows Python3.12.7常规进程下50通过/3既有warnings（8.89s）；新增13个参数场景。完整runner341通过/1 POSIX跳过/3既有warnings（20.16s）。报告使用真实生成服务/候选校验、真实SDK+MockTransport，统计/检索/存储/事务为替身；Ask服务为替身并实际调用同一SDK适配器。断言第一次wire后发生下游失败，后续embedding不产生新wire；成功和拒答允许下一次聊天，取消/关闭时后台turn已退出。首轮专项49通过/1失败揭示终态标志与asyncio.wait局部变量重名，修正后通过；沙箱专项无有效统计被中断，不计通过。

这些是直接驱动SSE生成器的离线回归，不是本次真实HTTP服务器、浏览器断网、数据库事务、旧报告保留或模型语义验收。鉴权/请求schema在流创建前拒绝、服务内部已恢复而最终成功的错误、未来运行器的审计失败尚不在此次停止覆盖内。跨进程完整运行器/96次总约束、人民币硬上限和真实调用授权仍未完成。

### 2026-10-28：单进程阶段编排与运行回执

`shared/acceptance/workflow.py::run_business_acceptance`是显式Python编排入口，没有CLI、默认网络transport或凭据读取。它持有一个`acceptance_adapters`上下文，按prepare → seed → repeat_seed → API启动 → exercise → audit → API关闭 → SDK关闭运行。调用方提供经过授权的数据准备、seed、浏览器/服务监听和数据库审计回调；这些是可信集成代码，必须使用传入的适配器/应用，不是安全沙箱。API由编排器创建并管理一次lifespan，exercise收到已经启动的app，不能再次启动lifespan或另启普通uvicorn进程。

`scripts/seed_phase14_demo_data.py::seed_demo_data(embedder=adapters.embedder)`现可借用同一Embedder，独立运行的旧默认保持不变。该脚本仍只生成10条合成mention，不处理公开真实评论，也不负责证明数据库为空/归本次拥有。已有关系库写入和Milvus写入非跨库原子事务；失败停止不会撤销之前已提交的数据。

每个阶段开始和返回时都检查共享停止标志；回调吞掉provider异常也不能继续下一阶段。失败/取消会锁定guard并传播原异常，停止后续阶段。Ask回执必须绑定同一run ID且恰好五轮；报告回执必须是同一报告范围的两次生成且时间递增；随后才调用精确数据库审计。仅通过回执结构不等于通过数据库或语义验收，audit回调必须在不匹配时抛错。关闭API/SDK失败也不能把整轮标为completed。

调用方预先创建`RunRecord(UUID)`，结束后可用`dataclasses.asdict(record)`序列化；即使异常/取消仍可读状态、阶段耗时、出站计数和provider报告token。只保存固定字段，不存回调输出、错误正文、密钥、prompt或评论；不自动写文件。record不得复用；chat/embedding额度不得超过既有拟定72/24，否则运行前拒绝，要求重新规划。此限制只覆盖经传入适配器的请求，尚未覆盖旧Playwright子进程启动器；费用仍为null、`monetary_cap_enforced=false`。

离线复现：`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_acceptance_workflow.py`。新增14场景：正常顺序与合计chat2/embedding3（含启动probe），prepare/seed/重复seed/启动/业务/审计/回执/关闭失败，取消、吞错、累计额度耗尽，以及真实seed函数两次注入（SQLAlchemy会话和Milvus替身、真实SDK+MockTransport）。完整Windows Python3.12.7隔离runner **355 passed/1 POSIX skipped/3既有warnings，18.39s**；全仓Ruff通过。首次沙箱专项无有效输出主动中止，不计通过；常规进程首批13场景9.48s通过，新增真实seed回归包含在完整结果内。

未启动真实HTTP监听/数据库/Milvus/浏览器，未调用真实模型、读取评论或配置凭据；没有重跑前端/容器/wheel。当前交付为单进程编排内核，尚需接入监听服务器、Playwright回执、公开样本准备和真实审计回调，不能称96次全流程约束或真实E2E已验收。所有入口仍须沿用空cwd/隔离环境，避免settings自动发现根.env；真实运行另行集中确认。

### 模型与费用依据（公开参考，不是实际账户配置）

2026-10-22读取[智谱官方API价格表](https://docs.bigmodel.cn/cn/guide/start/pricing)：`glm-4-flashx-250414`非缓存输入/输出均0.1元/百万token，`embedding-3`标准输入0.5元/百万token。[Embedding-3说明](https://docs.bigmodel.cn/cn/guide/models/embedding/embedding-3)支持1024维及最多64条文本批量。代码默认模型恰为这两个，但未读取本机.env核对有效配置，也未用真实请求验证可用性。

当前只保存价格快照/直接来源；总费用仍未知，不能用请求数直接乘token单价。下一步结合明确样本、实际provider/模型、输入及输出token边界、失败/重试策略给出可审阅清单和预算，再集中确认真实运行。不购买、不改凭据、不启worker/judge或发布。

### 2026-10-29：同一应用的回环HTTP监听桥

`shared/acceptance/server.py`提供`acceptance_server(app)`与`http_exercise(callback)`。编排器已持有app lifespan，监听桥以lifespan=off借用该app，预绑定127.0.0.1随机端口并把同一个socket交给Uvicorn，无子进程、信号处理或二次启动探测。HTTP/浏览器回调收到base URL与run ID，返回原有Ask/报告回执；可通过`exercise=http_exercise(callback)`接入workflow。回调必须使用传入URL，不启动旧Playwright API webServer。这里只接通服务器适配协议，未改现有Playwright配置或运行浏览器。

真实回环HTTP测试收到SSE的shared/done事件，成功、异常与取消退出后监听器is_serving为false，后续连接失败，外层lifespan只开始/结束各一次。启动异常不暴露URL。编排集成使用真实FastAPI/Uvicorn/httpx/OpenAI SDK与MockTransport，存储为替身：启动embedding1次、HTTP诊断路由chat1次，累计计数相同，app仅创建一次、DB仅关闭一次。诊断路由只存在测试中。

Windows Python3.12.7常规进程执行`.venv/Scripts/python.exe scripts/run_backend_tests.py`：360 passed/1 POSIX skipped/3既有warnings，96.94s；`.venv/Scripts/python.exe -m ruff check backend pipelines shared scripts tests conftest.py ops`通过。首轮专项3失败/1通过：成功HTTP之后，关闭端口返回ConnectTimeout而非测试预期的ConnectError；补充监听器关闭的直接断言，并接受两种平台连接失败表现，未放宽成功请求/SSE/生命周期断言。禁用不需要的WebSocket协议，避免加载额外协议插件。

未验证真实数据库/Milvus/模型、Ask/报告HTTP业务端点、Playwright、跨平台Linux新监听测试、公开样本、预算与发布；未复跑本机前端/容器/wheel。真实监听和SSE不等于浏览器或真实语义验收。使用Uvicorn显式startup/shutdown生命周期接口，依赖升级需保持该回归；优雅关闭最多等待后台请求2秒，尚未专项验证持续不退出的流。下一步接Playwright回执及精确落库审计，继续核实数据条件与模型/token费用清单，真实运行另确认。

### 2026-10-30：借用应用会话的数据库审计回调

`shared/acceptance/audit.py` 的 `database_audit(get_db_context, expectations=..., allowed_mention_ids=...)` 返回可直接传给 `run_business_acceptance(audit=...)` 的回调。必须传入当前数据集的五轮预期与允许引用ID，不隐式使用202403合成样本。调用者应使用已启动应用的会话上下文；回调不调用init_db/close_db，也不创建模型客户端。这里只执行SELECT，事务与连接由传入上下文管理；并非数据库权限级只读沙箱。

Ask与报告回执先检查run ID和结构；按session ID读取整个会话并按created_at/id排序，复用audit_turns核对消息数量、身份、prompt、工具、状态和引用范围，然后按SKU/周查询当前报告，复用audit_report核对报告ID、最终时间与内容SHA256。多余会话消息也会失败，不能只查询回执列出的消息来规避；摘要校验不判断语义质量。失败由workflow锁定共享guard并关闭外层资源，不撤销已提交数据。不记录正文/JWT。

专项命令：`.venv/Scripts/python.exe scripts/run_backend_tests.py tests/test_acceptance_workflow.py`，Windows Python3.12.7常规进程、空cwd/应用环境隔离，20 passed / 2既有warnings，81.02s。新增五个编排集成场景：正常、额外消息、引用越界、旧报告、查询异常；断言会话查询参数与排序、会话退出、失败状态/停止标记、DB仅关闭一次、无审计模型请求（仅启动embedding一次）。真实SQLAlchemy语句/审计函数/workflow/SDK+MockTransport，查询返回与报告仓库为替身；尚无真实PostgreSQL/Milvus/HTTP业务/浏览器/模型/公开数据验收。本机前端、容器及wheel未复跑。下一步将Playwright回执接入同一监听URL，补实际隔离数据库审计运行；数据条件及真实调用授权仍须满足。
