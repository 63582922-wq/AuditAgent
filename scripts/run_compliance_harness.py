#!/usr/bin/env python3
"""运行会议合规 Agent Harness：导入 FX 案件并执行完整分析链路。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal, init_db
from app.services.agent.harness import ComplianceHarness
from app.services.seed import seed_rules


def main() -> int:
    parser = argparse.ArgumentParser(description="FXPG 会议合规 Agent Harness")
    parser.add_argument(
        "case_path",
        nargs="?",
        default=str(ROOT / "FX"),
        help="案件目录（默认 ./FX）",
    )
    parser.add_argument("--name", help="项目名称")
    parser.add_argument("--import-only", action="store_true", help="仅导入，不运行分析")
    parser.add_argument("--skip-orchestrator", action="store_true", help="跳过 Orchestrator，仅跑合规规则")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        seed_rules(db)
        harness = ComplianceHarness(db)
        case = Path(args.case_path).expanduser().resolve()
        if not case.is_dir():
            print(f"错误：案件目录不存在 {case}", file=sys.stderr)
            return 1

        if args.import_only:
            project_id, profile = harness.import_case(case, args.name)
            print(json.dumps({"project_id": project_id, "meeting_code": profile.get("meeting_code")}, ensure_ascii=False, indent=2))
            return 0

        result = harness.run_case_folder(case, args.name) if not args.skip_orchestrator else None
        if args.skip_orchestrator:
            project_id, _ = harness.import_case(case, args.name)
            result = harness.run(project_id, skip_orchestrator=True)

        print(
            json.dumps(
                {
                    "project_id": result.project_id,
                    "status": result.status,
                    "meeting_code": result.meeting_code,
                    "finding_count": result.finding_count,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
