"""Run isolated Docker startup contracts using a TEST embedding provider.

No local .env, real credentials, ingestion, scheduler job or model is used.
The generated project must not exist; only its own containers/volumes are removed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def isolated_environment(api_port: int, web_port: int) -> dict[str, str]:
    # Preserve Docker transport/credential-helper and OS settings, not application
    # or Compose interpolation variables inherited from the developer shell.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("VOC_", "COMPOSE_"))
    }
    env.update(VOC_API_PORT=str(api_port), VOC_WEB_PORT=str(web_port))
    return env


def request(url: str, *, body=None, token=None, status=200):
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        if response.status != status:
            raise AssertionError(
                f"{req.get_method()} {url}: expected {status}, got {response.status}"
            )
        data = response.read()
        return (
            json.loads(data)
            if "application/json" in response.headers.get("Content-Type", "")
            else data.decode()
        )


class Smoke:
    def __init__(self, project: str, api_port: int, web_port: int):
        if not re.fullmatch(r"voc-smoke-[a-z0-9-]+", project):
            raise ValueError(
                "Project must start voc-smoke- and contain lowercase letters/digits/hyphens"
            )
        self.project = project
        self.environment = isolated_environment(api_port, web_port)
        self.api = f"http://127.0.0.1:{api_port}"
        self.web = f"http://127.0.0.1:{web_port}"
        self.base = [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / "ops/compose.empty.env"),
            "-p",
            project,
            "-f",
            str(ROOT / "ops/docker-compose.yml"),
            "-f",
            str(ROOT / "ops/compose.smoke.yml"),
            "--profile",
            "smoke",
        ]

    def run(self, args, *, check=True, timeout=240):
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=self.environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        if check and result.returncode:
            # Only the isolated stack's test configuration can appear here.
            raise RuntimeError(
                f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stdout[-6000:]}"
            )
        return result

    def compose(self, *args, **kwargs):
        return self.run([*self.base, *args], **kwargs)

    def state(self, service):
        cid = self.compose("ps", "-a", "-q", service).stdout.strip()
        if not cid:
            return None
        return json.loads(
            self.run(["docker", "inspect", "--format", "{{json .State}}", cid]).stdout
        )

    def provider(self, dimensions=None):
        code = (
            "import urllib.request,json; "
            + (
                "r=urllib.request.Request('http://127.0.0.1:8080/dimensions',"
                f"data=b'{{\"dimensions\":{dimensions}}}',headers={{'Content-Type':'application/json'}}); "
                if dimensions is not None
                else "r='http://127.0.0.1:8080/stats'; "
            )
            + "print(urllib.request.urlopen(r,timeout=5).read().decode())"
        )
        return json.loads(
            self.compose("exec", "-T", "mock-embedding", "python", "-c", code).stdout
        )

    def verify_http(self):
        assert request(self.api + "/health")["status"] == "healthy"
        assert len(request(self.api + "/api/skus")) == 5
        assert request(self.api + "/api/weeks") == []
        request(self.api + "/api/overview?week_id=202601", status=404)
        request(self.api + "/api/auth/me", status=401)
        request(self.api + "/api/auth/login", body={"password": "wrong"}, status=401)
        login = request(
            self.api + "/api/auth/login", body={"password": "local-container-only"}
        )
        assert (
            request(self.api + "/api/auth/me", token=login["access_token"])["subject"]
            == "admin"
        )
        html = request(self.web + "/overview")
        assert "VOC Intelligence" in html
        assets = set(
            re.findall(r'(?:src|href)="([^"?]+\.(?:js|css))(?:\?[^\"]*)?"', html)
        )
        assert any(path.endswith(".css") for path in assets)
        assert any(path.endswith(".js") for path in assets)
        bundles = "".join(
            request(self.web + path) for path in assets if path.startswith("/")
        )
        assert self.api in bundles, "Browser API URL missing from built JavaScript"
        assert "http://api:8000" not in bundles
        # Development CORS must permit the actual loopback browser origin.
        with urlopen(
            Request(self.api + "/api/skus", headers={"Origin": self.web}), timeout=10
        ) as response:
            assert response.headers.get("Access-Control-Allow-Origin") == self.web
        print(
            "PASS: health, empty dashboard, auth, CORS, web assets and browser API URL",
            flush=True,
        )

    def execute(self, build=False):
        # Refuse both stale containers and stale volumes BEFORE acquiring ownership.
        for resource in ("ps", "volume"):
            args = (
                ["docker", "ps", "-a", "-q"]
                if resource == "ps"
                else ["docker", "volume", "ls", "-q"]
            )
            if self.run(
                [*args, "--filter", f"label=com.docker.compose.project={self.project}"]
            ).stdout.strip():
                raise RuntimeError(
                    "Project already has resources; refusing to use or clean them"
                )
        self.compose("config", "--quiet")
        if build:
            print("Building isolated smoke images...", flush=True)
            self.compose("build", "api", "web", "mock-embedding", timeout=1200)
        self.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "python",
                "voc-agent-backend:local",
                "-c",
                "import os, pathlib, importlib.util; assert os.getuid()!=0; "
                "assert not pathlib.Path('/app/.env').exists(); "
                "assert not pathlib.Path('/app/backend').exists(); "
                "assert 'site-packages' in importlib.util.find_spec('backend.app.main').origin",
            ]
        )
        self.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "alembic",
                "voc-agent-backend:local",
                "-c",
                "/app/alembic.ini",
                "history",
            ]
        )
        self.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "node",
                "voc-agent-frontend:local",
                "-e",
                "if(process.getuid()===0)process.exit(1)",
            ]
        )
        print(
            "PASS: non-root images and installed wheel migration resources", flush=True
        )
        owned = False
        try:
            owned = True
            self.compose(
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "240",
                "api",
                "web",
                "smoke-ingress",
                timeout=360,
            )
            assert self.state("init")["ExitCode"] == 0
            assert self.state("worker") is None, "Worker must not start by default"
            self.verify_http()
            assert self.provider()["embedding_requests"] >= 1
            self.compose("run", "--rm", "--no-deps", "init")
            count = self.compose(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "voc",
                "-d",
                "voc",
                "-Atc",
                "SELECT count(*), count(DISTINCT sku_code) FROM skus",
            ).stdout.strip()
            assert count == "5|5", count
            print(
                "PASS: repeated migration/seed retains exactly five unique SKUs",
                flush=True,
            )
            cid = self.compose("ps", "-q", "api").stdout.strip()
            network_ids = json.loads(
                self.run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{json .NetworkSettings.Networks}}",
                        cid,
                    ]
                ).stdout
            )
            assert len(network_ids) == 1
            for network in network_ids.values():
                assert (
                    self.run(
                        [
                            "docker",
                            "network",
                            "inspect",
                            "--format",
                            "{{.Internal}}",
                            network["NetworkID"],
                        ]
                    ).stdout.strip()
                    == "true"
                )
            print("PASS: API attached only to an internal Docker network", flush=True)

            self.compose("--profile", "worker", "up", "-d", "worker")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if (
                    "Scheduler 已启动"
                    in self.compose("logs", "--no-color", "worker").stdout
                ):
                    break
                time.sleep(1)
            else:
                raise AssertionError("Opt-in worker did not initialize its scheduler")
            assert self.state("worker")["Running"]
            self.compose("stop", "worker")
            print(
                "PASS: opt-in worker initializes and stops; no scheduled job invoked",
                flush=True,
            )

            self.provider(768)
            self.compose("restart", "api")
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline and self.state("api")["Running"]:
                time.sleep(1)
            state = self.state("api")
            assert not state["Running"] and state["ExitCode"] != 0, state
            assert (
                "dimension mismatch" in self.compose("logs", "--no-color", "api").stdout
            )
            print(
                "PASS: real API startup rejects the 768-dimensional test provider",
                flush=True,
            )
            self.provider(1024)
            self.compose(
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "120",
                "api",
                "web",
                "smoke-ingress",
            )
            self.verify_http()

            self.compose("stop", "api", "web")
            fail = [
                *self.base,
                "-f",
                str(ROOT / "ops/compose.init-failure.yml"),
                "up",
                "-d",
                "api",
                "worker",
            ]
            result = self.run(fail, check=False)
            assert result.returncode != 0, "Failed init unexpectedly accepted"
            assert self.state("init")["ExitCode"] == 23
            for service in ("api", "worker"):
                state = self.state(service)
                assert state is None or not state["Running"], (
                    f"{service} bypassed failed init"
                )
            print("PASS: failed init blocks both API and opt-in worker", flush=True)
            self.compose(
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "120",
                "api",
                "web",
                "smoke-ingress",
            )
            self.verify_http()
            print("PASS: restored init allows application recovery", flush=True)
        except BaseException:
            logs = self.compose(
                "logs", "--no-color", "--tail", "35", "api", "init", check=False
            )
            print(logs.stdout[-6000:], flush=True)
            raise
        finally:
            if owned:
                # Unique project verified empty above; never root Compose or global prune.
                self.compose(
                    "--profile",
                    "worker",
                    "down",
                    "--volumes",
                    "--remove-orphans",
                    timeout=120,
                )
                print(f"Cleaned only owned smoke project {self.project}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=f"voc-smoke-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--api-port", type=int, default=18000)
    parser.add_argument("--web-port", type=int, default=13000)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    Smoke(args.project, args.api_port, args.web_port).execute(build=args.build)


if __name__ == "__main__":
    main()
