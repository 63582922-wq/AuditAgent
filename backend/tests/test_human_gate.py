from app.models import Risk
from app.services.agent.human_gate import evaluate_human_gate


def _risk(level: str, manual: bool) -> Risk:
    return Risk(
        project_id="p1",
        risk_id="R-test",
        risk_category="税务风险",
        risk_level=level,
        manual_review_required=manual,
        problem="测试",
        evidence_json={},
        suggestion="建议",
    )


def test_human_gate_pauses_on_high_count():
    risks = [_risk("高", True), _risk("高", True), _risk("高", True)]
    gate = evaluate_human_gate(risks)
    assert gate.pause
    assert gate.manual_count == 3


def test_human_gate_passes_small_set():
    risks = [_risk("低", False)]
    gate = evaluate_human_gate(risks)
    assert not gate.pause
