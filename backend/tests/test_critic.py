from app.services.agent.critic import validate_risk_evidence, apply_critic_to_risks


def test_critic_flags_unverified_numbers():
    risk = {
        "risk_id": "EXP-001-2",
        "analysis": "该笔费用 128000 元缺少发票，需核实。",
        "evidence_json": {"amount": 5000},
    }
    result = validate_risk_evidence(risk)
    assert not result.valid
    assert result.flags


def test_critic_passes_matching_numbers():
    risk = {
        "risk_id": "EXP-001-3",
        "analysis": "金额 128000 与台账一致，但仍缺发票。",
        "evidence_json": {"amount": 128000},
    }
    result = validate_risk_evidence(risk)
    assert result.valid


def test_apply_critic_marks_manual_review():
    risks = [{"risk_id": "R1", "analysis": "x", "confidence": 0.9, "manual_review_required": False}]
    results = [validate_risk_evidence({**risks[0], "analysis": "金额 999999 异常", "evidence_json": {}})]
    out = apply_critic_to_risks(risks, results)
    assert out[0]["manual_review_required"] is True
