"""Repository-wide pytest configuration."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

_GENERATED_BASETEMP = pytest.StashKey[Path]()


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Avoid reusing temp roots whose Windows ACL belongs to another account."""
    if config.option.basetemp is not None:
        return

    basetemp = Path(config.rootpath) / f".pytest-tmp-{uuid4().hex}"
    config.option.basetemp = str(basetemp)
    config.stash[_GENERATED_BASETEMP] = basetemp


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(
    session: pytest.Session, exitstatus: pytest.ExitCode
) -> None:
    """Clean the generated temp root after a successful test session."""
    basetemp = session.config.stash.get(_GENERATED_BASETEMP, None)
    if exitstatus == pytest.ExitCode.OK and basetemp is not None:
        shutil.rmtree(basetemp, ignore_errors=True)
