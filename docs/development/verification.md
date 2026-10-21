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

这部分继续沿用 README 的隔离数据库/collection 和 provider 说明。API 必须满足迁移、基础 seed、锁定 SKU、Milvus 与维度契约后才能启动；仅检查 YAML 或单测通过不能替代真实启动。现有 Playwright API 命令是 Windows 路径，不能直接移到 Linux 门禁；后续单独做跨平台改造。不得将 CI 临时资源清理命令用于用户现有卷或数据库。

10-20 时镜像与编排尚未验证；10-21 新增的容器启动门禁见下节。真实模型调用、凭据配置、付费资源和公网发布按确认范围执行。

## 容器启动与失败恢复（10-21 新增）

操作与边界见 [ops 运行手册](../../ops/README.md)，确认取舍见 [ADR 0001](decisions/0001-container-startup-contract.md)。从仓库根执行：

```sh
python scripts/run_container_smoke.py --build
```

使用独立随机项目与空 env-file，内部测试网络、测试 embedding 服务；覆盖正常启动、重复迁移/seed、1024/768 维契约、init 失败阻断与恢复、登录/空 dashboard/CORS 和前端静态资源。只清理自己新建的项目和卷，不操作根 Compose 或旧数据。完整命令和端口变化后的重建方式在 ops 手册。

该流程进入独立的 [Container delivery workflow](../../.github/workflows/containers-ci.yml)，不需要模型密钥。原普通双端 CI 依旧不启动存储或 provider；容器 CI 的通过也只证明测试依赖下的启动契约，不能代替真实模型、Ask/报告效果、调度任务运行、Playwright 浏览器交互或公网验收。本地 Docker Hub/ECR 下载失败与远端验收分别记录在 [10-21 daily](daily/2026-10-21.md)，不要把远端通过写成本地已能复跑。
