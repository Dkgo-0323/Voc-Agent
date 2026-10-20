"""Keep wheel smoke checks inside the selected virtual environment on POSIX."""

import os
import sys
import venv
from zipfile import ZipFile

import pytest

from scripts import check_distribution


@pytest.mark.skipif(os.name == "nt", reason="POSIX virtual environments use interpreter symlinks")
def test_distribution_check_preserves_virtual_environment(tmp_path, monkeypatch) -> None:
    environment = tmp_path / "venv"
    venv.create(environment, with_pip=False, symlinks=True)
    python = environment / "bin" / "python"
    assert python.is_symlink()
    wheel = tmp_path / "fixture.whl"
    with ZipFile(wheel, "w") as archive:
        for name in check_distribution.REQUIRED_FILES:
            archive.writestr(name, "")
        archive.writestr("backend/app/db/migrations/versions/fixture.py", "")

    # Run a real child interpreter; dereferencing its symlink would change prefix.
    monkeypatch.setattr(
        check_distribution,
        "IMPORT_CHECK",
        f"import sys; assert sys.prefix == {str(environment)!r}, sys.prefix",
    )
    monkeypatch.setattr(
        sys, "argv", ["check_distribution.py", str(wheel), "--python", str(python)]
    )
    check_distribution.main()
