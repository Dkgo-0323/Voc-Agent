"""Run deterministic tests without local .env files or inherited app settings."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Keep OS process/runtime settings, but exclude application credentials/config.
OS_ENVIRONMENT_KEYS = {
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "CI", "GITHUB_ACTIONS",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", choices=("fd", "sys", "no"), default="fd")
    parser.add_argument("paths", nargs="*", type=Path, help="Test paths, relative to repository root")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    paths = [str((repository / path).resolve()) for path in args.paths] or [str(repository / "tests")]
    environment = {
        key: value for key, value in os.environ.items()
        if key.upper() in OS_ENVIRONMENT_KEYS
    }
    environment["PYTHONPATH"] = str(repository)
    # The cwd is empty, so Settings cannot discover a developer's .env file.
    # Use a checkout-owned temp location to avoid cross-account Windows temp ACLs.
    temporary_root = repository / "dist"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voc-unit-tests-", dir=temporary_root) as directory:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest", "-q", f"--capture={args.capture}",
                "-c", str(repository / "pyproject.toml"),
                "--rootdir", str(repository), *paths,
            ],
            cwd=directory,
            env=environment,
            check=False,
        )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
