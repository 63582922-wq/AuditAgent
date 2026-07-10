from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_compliance_harness.py"
    spec = importlib.util.spec_from_file_location("run_compliance_harness", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_import_only_cli_reports_project_and_meeting(monkeypatch, tmp_path, capsys) -> None:
    module = _load_script_module()
    case_dir = tmp_path / "Remote_A1P260307357_20260506_Luo, Amy Yun_Supporting"
    case_dir.mkdir()

    class FakeDB:
        def close(self) -> None:
            pass

    class FakeHarness:
        def __init__(self, db):
            self.db = db

        def import_case(self, case_path, project_name=None):
            assert Path(case_path) == case_dir.resolve()
            assert project_name == "导入测试"
            return "project-1", "meeting-1", {"meeting_code": "A1P260307357"}

    monkeypatch.setattr(module, "init_db", lambda: None)
    monkeypatch.setattr(module, "seed_rules", lambda db: None)
    monkeypatch.setattr(module, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(module, "ComplianceHarness", FakeHarness)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_compliance_harness.py",
            str(case_dir),
            "--name",
            "导入测试",
            "--import-only",
        ],
    )

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "project_id": "project-1",
        "meeting_id": "meeting-1",
        "meeting_code": "A1P260307357",
    }
