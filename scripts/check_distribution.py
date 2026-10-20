"""Verify wheel contents and installed imports without the source checkout.

Install the wheel and locked runtime dependencies into a separate environment,
then pass its Python executable with --python. This script uses only stdlib.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

REQUIRED_FILES = {
    "backend/app/main.py",
    "backend/worker/main.py",
    "backend/app/db/seed.py",
    "backend/app/db/migrations/env.py",
    "backend/app/db/migrations/script.py.mako",
    "pipelines/config/targets.py",
    "pipelines/embedding/embedder.py",
    "shared/eval/rag_eval.py",
    "shared/eval/semantic_golden.py",
}
FORBIDDEN_PARTS = {".git", ".venv", "node_modules", "__pycache__", "artifacts", "data", "tests"}

IMPORT_CHECK = """
import importlib
import importlib.metadata
from pathlib import Path
import socket
import sysconfig

def deny_network(*args, **kwargs):
    raise RuntimeError("Distribution smoke check must not connect to services")

socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network
roots = {Path(sysconfig.get_path(name)).resolve() for name in ("purelib", "platlib")}
modules = (
    "backend.app.main",
    "backend.worker.main",
    "backend.app.db.seed",
    "pipelines.ingestion.amazon_loader",
    "shared.eval.rag_eval",
    "shared.eval.fixture_execution",
)
for name in modules:
    module = importlib.import_module(name)
    path = Path(module.__file__).resolve()
    if not any(path.is_relative_to(root) for root in roots):
        raise RuntimeError(f"{name} resolved outside installed site-packages: {path}")
    print(f"Installed import OK: {name}", flush=True)
print("Distribution version:", importlib.metadata.version("voc-agent"))
"""


def check_contents(wheel: Path) -> None:
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = REQUIRED_FILES - names
    if missing:
        raise ValueError(f"Wheel is missing required runtime files: {sorted(missing)}")
    if not any(
        name.startswith("backend/app/db/migrations/versions/") and name.endswith(".py")
        for name in names
    ):
        raise ValueError("Wheel contains no Alembic migration revisions")
    forbidden = []
    for name in names:
        path = PurePosixPath(name)
        if FORBIDDEN_PARTS.intersection(path.parts) or path.name.startswith(".env"):
            forbidden.append(name)
    if forbidden:
        raise ValueError(f"Wheel contains local/private artifacts: {sorted(forbidden)}")
    print(f"Wheel contents OK: {wheel.name}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--python", default=sys.executable, help="Python in the wheel installation environment")
    args = parser.parse_args()
    check_contents(args.wheel.resolve())
    environment = os.environ.copy()
    environment.update(
        APP_ENV="development",
        DATABASE_URL="postgresql+asyncpg://test:test@127.0.0.1:9/test",
        MILVUS_HOST="127.0.0.1",
        MILVUS_PORT="9",
        LLM_API_KEY="",
        OPENAI_API_KEY="",
        EMBEDDING_API_KEY="",
        LLM_BASE_URL="http://127.0.0.1:9/v1",
        EMBEDDING_BASE_URL="http://127.0.0.1:9/v1",
        JWT_SECRET_KEY="distribution-smoke-only",
        ADMIN_PASSWORD="distribution-smoke-only",
    )
    # -I removes checkout/PYTHONPATH imports. An empty cwd also prevents .env reads.
    with tempfile.TemporaryDirectory(prefix="voc-distribution-") as directory:
        subprocess.run(
            [str(Path(args.python).resolve()), "-I", "-c", IMPORT_CHECK],
            cwd=directory,
            env=environment,
            check=True,
            timeout=120,
        )


if __name__ == "__main__":
    main()
