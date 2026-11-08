import json
from pathlib import Path

from scripts.run_conversation_e2e import save_report


def test_report_replace_recovers_from_temporary_windows_file_lock(
    tmp_path, monkeypatch
):
    path = tmp_path / "report.json"
    path.write_text('{"old":true}', encoding="utf-8")
    original = Path.replace
    attempts = 0

    def replace(self, target):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
            raise PermissionError("temporarily locked")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("scripts.run_conversation_e2e.sleep", lambda _: None)
    save_report(path, {"complete": True})
    assert attempts == 3
    assert json.loads(path.read_text(encoding="utf-8")) == {"complete": True}
