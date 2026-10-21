# Local container delivery

This is a local development/startup contract, not a public production deployment.
The root Compose and existing `voc_*` containers/volumes are separate and must not
be stopped, migrated, seeded or removed by these commands.

## Reproducible startup test (no real provider)

From the repository root, with Docker Engine and Compose 2.24.4+ available:

```sh
python scripts/run_container_smoke.py --build
```

Use Python 3.11+ (stdlib only). The command generates an unused `voc-smoke-*`
project, uses an explicit empty environment file instead of the repository `.env`,
and fixes placeholder credentials. It builds API/worker, Next standalone and the
**test-only fixed-vector embedding server**. The API's normal startup and 1024-D
contract checks remain enabled. The test network is internal, with no external
provider configured. API/worker/provider remain only on the internal network.
A **test-only ingress helper** connects that network to a separate bridge and
publishes only the two loopback API/web ports; it forwards only fixed API/web
targets, rejects arbitrary proxy destinations, and is not a production or SSE
proxy. The smoke override resets direct application ports with `!reset []`.
The base application Compose does not add this helper. Worker is not started by
ordinary `up`.

The runner checks migration/seed on a new database and after repetition, five
unique SKUs, API health, login/rejection/identity, empty dashboard responses,
loopback CORS, served JS/CSS, and the browser-reachable API URL in the JS bundle.
It forces a 768-D response to prove startup rejection, restores 1024-D, then forces
init exit 23 to prove API and opt-in worker are blocked, and tests recovery.
It also explicitly starts/stops the optional worker to verify scheduler
initialization, without manually invoking a scheduled job.
These are HTTP/static-asset startup checks, not browser interaction or semantic
Ask/report quality tests. `/health` continuously checks PostgreSQL only.

Finally it removes **only the fresh project it owns**, including that project's
volumes. Existing project containers or volumes cause refusal before cleanup is
armed. No global prune, root Compose cleanup or old database is used. Ports
18000/13000 must be free. With custom ports, pass `--api-port` / `--web-port` and
`--build` so the frontend's public API URL is rebuilt to match.

The [container workflow](../.github/workflows/containers-ci.yml) runs this same
contract on Linux without secrets. Windows and CI results are recorded separately
in the [daily log](../docs/development/daily/2026-10-21.md).

## Keep the empty local UI running for inspection

These explicit commands create a separate local test stack and leave it running:

```sh
docker compose --env-file ops/compose.empty.env -p voc-demo -f ops/docker-compose.yml -f ops/compose.smoke.yml --profile smoke up --build -d --wait
```

Open <http://127.0.0.1:13000/overview>; API health is at
<http://127.0.0.1:18000/health>. The local-only password is
`local-container-only`. The database has five SKU records and no reviews/weekly
data; the provider returns fake vectors and has no chat endpoint. This stack is
useful for startup/UI inspection, not AI answers or semantic retrieval. Do not
expose it to a public interface. Stop it using the same explicit files and
project name; deleting its volumes is optional and loses only that project's data.

## Images and configuration

- Backend: `docker build -f ops/Dockerfile.backend -t voc-agent-backend:local .`.
  Python 3.12, uv 0.11.8, locked runtime dependencies, wheel install and six
  isolated imports during build. The final image runs as UID 10001, without the
  source checkout, development tools, local `.env` or data. Alembic resolves
  `backend:app/db/migrations` from the installed wheel.
- Frontend: `docker build -t voc-agent-frontend:local frontend`. Node 22 and
  `npm ci`; standalone plus public/static files, running as the node user.
  `NEXT_PUBLIC_API_BASE_URL` is a build argument, defaulting to
  `http://127.0.0.1:18000`. It must be reachable by the browser, not Docker's
  `api:8000`. Changing this URL requires a new build; runtime environment changes
  do not rewrite browser bundles.
- Base tags are explicit version families, not immutable releases. Build logs
  record resolved image digests; release-grade pinning/resource review belongs
  to the later deployment plan.
- Optional build arguments `PYTHON_IMAGE` / `NODE_IMAGE` (Compose variables
  `VOC_PYTHON_IMAGE` / `VOC_NODE_IMAGE`) allow an explicitly chosen trusted image
  source. Docker's official [ECR Public gallery](https://gallery.ecr.aws/docker/)
  distributes Python/Node images. Both Docker Hub and ECR failed to download from
  this workstation during implementation; changing registry is not a guaranteed
  fix. No daemon/proxy/TLS settings were modified. The smoke runner intentionally
  clears inherited VOC/COMPOSE variables; direct Compose builds can use these
  overrides, then run the smoke command without `--build`.
- The base `docker-compose.yml` has no test provider. Without explicitly supplied
  provider configuration its API fails at startup; it does not silently swap in
  fake vectors. Do not configure real credentials or make real calls under this
  test procedure. The dedicated `compose.smoke.yml` enables the explicit fake.
- Init runs once before API/worker and upserts the five locked SKUs. Never point
  it at an existing user database. Worker requires explicit `--profile worker`;
  a running worker schedules Sunday 02:00 UTC processing. Single-process
  `max_instances=1` is not a distributed lock. This delivery does not validate
  scheduler execution or multi-worker operation.
- Milvus/Postgres/etcd versions match the existing development stack. The old
  upstream MinIO image can no longer be pulled, so only this new isolated stack
  uses `milvusdb/minio:RELEASE.2024-12-18T13-15-44Z` and `mc ready local`, following
  the [Milvus-maintained development Compose](https://github.com/milvus-io/milvus/blob/06dec9a0e063aa9853da2000e555888fb491cb39/deployments/docker/dev/docker-compose.yml).
  The root Compose and its existing MinIO data/version are untouched. Only application ports
  are published, on loopback; PostgreSQL/Milvus/MinIO/etcd have no published host
  ports. All storage uses project-scoped named volumes.

Real provider/data/Ask/report verification remains ENG-05B. Public deployment
requires a separate confirmed plan for authentication, access limits, CORS,
HTTPS, budget, secrets and rollback.
