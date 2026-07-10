import pytest

from app.models import AgentActionProposal, AgentRunLog, AnalysisJob, FileRecord, LearningProposal, Meeting, Memory, Output, ParsedDocument, Project, Risk
from app.services.embedding_service import embed_memory_content
from app.services.agent.action_executor import approve_agent_action
from app.services.agent.main_chat import run_main_agent_chat


def _case(db):
    project = Project(name="主 Agent 对话测试", status="active")
    db.add(project)
    db.commit()
    db.refresh(project)

    meeting = Meeting(project_id=project.id, meeting_code="A1P-CHAT", status="completed")
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    db.add(
        FileRecord(
            project_id=project.id,
            meeting_id=meeting.id,
            file_name="签到表.pdf",
            file_type="pdf",
            document_category="sign_in",
            storage_path="/tmp/sign-in.pdf",
            parse_status="parsed",
        )
    )
    db.add(
        Risk(
            project_id=project.id,
            meeting_id=meeting.id,
            risk_id="CHAT-001",
            risk_category="meeting_compliance",
            risk_level="中",
            risk_score=60,
            problem="缺少讲者证明材料",
            evidence_json={"files": ["签到表.pdf"]},
            suggestion="补充讲者资质证明",
            manual_review_required=True,
            confidence=0.82,
            status="pending",
        )
    )
    db.add(
        Output(
            project_id=project.id,
            meeting_id=meeting.id,
            output_type="finding_pdf",
            file_name="Finding.pdf",
            storage_path="/tmp/finding.pdf",
        )
    )
    db.add(
        AnalysisJob(
            project_id=project.id,
            meeting_id=meeting.id,
            status="completed",
            current_step="completed",
            progress_pct=100,
        )
    )
    db.commit()
    return project, meeting


def _cleanup_case(db, project_id: str):
    for model in (AgentActionProposal, LearningProposal, AgentRunLog, AnalysisJob, Output, Risk, ParsedDocument, FileRecord, Meeting):
        db.query(model).filter_by(project_id=project_id).delete()
    db.query(Project).filter_by(id=project_id).delete()
    for text in (
        "交付前必须先解释缺资料原因",
        "以后交付前先给我缺资料清单",
        "交付前必须先列出缺资料、证据不足和下一步",
        "手写到场时间低置信时不能判通过",
    ):
        db.query(Memory).filter(Memory.content.contains(text)).delete(synchronize_session=False)
    db.query(Memory).filter(Memory.content.contains("交付前必须先")).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def chat_case(db):
    project, meeting = _case(db)
    try:
        yield project, meeting
    finally:
        _cleanup_case(db, project.id)


def test_main_agent_chat_fallback_uses_case_context_and_logs(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="是否需要补充资料？",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.mode == "fallback"
    assert "资料 1 份" in out.reply
    assert "Finding 1 条" in out.reply
    assert any(action.id == "files" for action in out.actions)
    assert db.query(AgentRunLog).filter_by(project_id=project.id, meeting_id=meeting.id, step="main_agent_chat").count() == 1


def test_main_agent_chat_current_facts_override_bad_case_memory(db, monkeypatch):
    project = Project(name="A1P事实优先测试", status="active")
    db.add(project)
    db.commit()
    db.refresh(project)

    meeting = Meeting(
        project_id=project.id,
        meeting_code="A1P260307357",
        status="completed",
        state_json={
            "meeting_case": {
                "meeting_code": "A1P260307357",
                "actual_sign_in_count": 6,
                "planned_attendees": 6,
                "attendance_delta": 0,
            },
            "present_categories": [
                "a1_meeting_export",
                "coordination_sms",
                "meeting_screenshot",
                "observation_confirmation",
                "sign_in_record",
            ],
            "missing_documents": [],
        },
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    for idx in range(3):
        db.add(
            FileRecord(
                project_id=project.id,
                meeting_id=meeting.id,
                file_name=f"签到表 ({idx + 1}).jpg",
                file_type="image",
                document_category="sign_in_record",
                storage_path=f"/tmp/sign-in-{idx}.jpg",
                parse_status="done",
            )
        )
    for category in ("a1_meeting_export", "coordination_sms", "meeting_screenshot", "observation_confirmation"):
        db.add(
            FileRecord(
                project_id=project.id,
                meeting_id=meeting.id,
                file_name=f"{category}.jpg",
                file_type="image",
                document_category=category,
                storage_path=f"/tmp/{category}.jpg",
                parse_status="done",
            )
        )
    db.add(
        Risk(
            project_id=project.id,
            meeting_id=meeting.id,
            risk_id="CMP-004",
            risk_category="meeting_compliance",
            risk_level="中",
            risk_score=50,
            problem="计划与实际时长不一致",
            evidence_json={"planned_duration_minutes": 30, "actual_duration_minutes": 36},
            suggestion="计划会议时长与实际观察时长差异较大，需在 Finding 中说明。",
            manual_review_required=False,
            confidence=0.92,
            status="pending",
        )
    )
    db.add(
        Memory(
            memory_type="case",
            content="案例[计划不一致] 签到人数与计划不符。实际签到人数为0，缺少签到表。",
            tags=["计划不一致", "adjudication", "高"],
            embedding_json=embed_memory_content(
                "案例[计划不一致] 签到人数与计划不符。实际签到人数为0，缺少签到表。",
                ["计划不一致", "adjudication", "高"],
            ),
        )
    )
    db.commit()
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="资料是否够？有没有缺签到表？",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert "结构化缺件清单 0 项" in out.reply
    assert "签到表 3 份" in out.reply
    assert "实际签到 6 人" in out.reply
    assert "当前仍有缺件" not in out.reply
    assert all("[case]" not in item for item in out.context["memories"])

    db.query(Memory).filter(Memory.content.contains("实际签到人数为0，缺少签到表")).delete(synchronize_session=False)
    db.commit()
    _cleanup_case(db, project.id)


def test_main_agent_chat_reports_vision_review_status(db, monkeypatch):
    project = Project(name="视觉复核对话测试", status="active")
    db.add(project)
    db.commit()
    db.refresh(project)

    meeting = Meeting(
        project_id=project.id,
        meeting_code="A1P-VISION",
        status="completed",
        state_json={
            "meeting_case": {"meeting_code": "A1P-VISION"},
            "present_categories": ["sign_in_record"],
            "missing_documents": [],
        },
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    file_record = FileRecord(
        project_id=project.id,
        meeting_id=meeting.id,
        file_name="签到表.jpg",
        file_type="image",
        document_category="sign_in_record",
        storage_path="/tmp/sign.jpg",
        parse_status="done",
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    db.add(
        ParsedDocument(
            project_id=project.id,
            meeting_id=meeting.id,
            file_id=file_record.id,
            document_type="sign_in_record",
            text_content="签到表 6人",
            content_json={
                "manual_review_required": True,
                "review_reasons": ["single_pass_high_risk_document"],
                "vision_consensus": {
                    "status": "needs_review",
                    "review_reasons": ["single_pass_high_risk_document"],
                },
                "field_confidence": {"actual_sign_in_count": 0.86},
            },
        )
    )
    db.commit()
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="这些图片识别靠谱吗？有没有手写或低置信需要复核？",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.context["current_facts"]["vision_manual_review_count"] == 1
    assert out.context["current_facts"]["vision_consensus_needs_review_count"] == 1
    assert "视觉复核 1 份" in out.reply
    assert "single_pass_high_risk_document" in out.reply

    _cleanup_case(db, project.id)


def test_main_agent_chat_uses_llm_when_available(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: True)
    monkeypatch.setattr(
        "app.services.agent.llm_client.chat_completion",
        lambda messages, temperature=0.2: {"role": "assistant", "content": "**这是基于当前会议上下文的开放式回答。**"},
    )

    out = run_main_agent_chat(
        db,
        message="解释一下目前为什么待验收",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.mode == "llm"
    assert out.reply == "这是基于当前会议上下文的开放式回答。"
    assert out.context["meeting_code"] == "A1P-CHAT"


def test_main_agent_chat_fixed_template_delivery_answer_is_deterministic(db, chat_case, monkeypatch):
    project, meeting = chat_case
    db.add(
        Output(
            project_id=project.id,
            meeting_id=meeting.id,
            output_type="fixed_template_excel",
            file_name="固定模板输出.xlsx",
            storage_path="/tmp/固定模板输出.xlsx",
        )
    )
    db.add(
        Output(
            project_id=project.id,
            meeting_id=meeting.id,
            output_type="deliverable_package",
            file_name="A1P-CHAT_RemoteObservation.zip",
            storage_path="/tmp/A1P-CHAT_RemoteObservation.zip",
        )
    )
    db.commit()

    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: True)
    monkeypatch.setattr(
        "app.services.agent.llm_client.chat_completion",
        lambda messages, temperature=0.2: {"role": "assistant", "content": "固定模板交付指 A1 会议导出和观察确认单。"},
    )

    out = run_main_agent_chat(
        db,
        message="固定模板交付在哪里？",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.mode == "fallback"
    assert "固定模板输出.xlsx" in out.reply
    assert "ZIP" in out.reply
    assert "A1 会议导出和观察确认单" not in out.reply
    assert any(action.id == "outputs" for action in out.actions)


def test_main_agent_chat_retrieves_relevant_long_term_memory(db, chat_case, monkeypatch):
    project, meeting = chat_case
    db.add(
        Memory(
            memory_type="user_preference",
            content="用户偏好：交付前必须先解释缺资料原因。",
            tags=["main_agent_chat_test", "deliverable", "preference"],
            embedding_json=embed_memory_content(
                "用户偏好：交付前必须先解释缺资料原因。",
                ["main_agent_chat_test", "deliverable", "preference"],
            ),
        )
    )
    db.commit()
    captured = {}

    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: True)

    def fake_chat_completion(messages, temperature=0.2):
        captured["messages"] = messages
        return {"role": "assistant", "content": "我会按你的交付偏好先解释缺资料原因。"}

    monkeypatch.setattr("app.services.agent.llm_client.chat_completion", fake_chat_completion)

    out = run_main_agent_chat(
        db,
        message="交付前先解释缺资料原因",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.context["memory_count"] >= 1
    assert any("交付前必须先解释缺资料原因" in item for item in out.context["memories"])
    assert "交付前必须先解释缺资料原因" in "\n".join(m["content"] for m in captured["messages"])


def test_main_agent_chat_persists_user_preference_memory(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="请记住：以后交付前先给我缺资料清单。",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.context["memory_write"]["written"] == 1
    saved = (
        db.query(Memory)
        .filter(Memory.memory_type == "user_preference", Memory.content.contains("以后交付前先给我缺资料清单"))
        .first()
    )
    assert saved is not None
    assert "以后交付前先给我缺资料清单" in saved.content
    assert "main_agent_chat" in saved.tags


def test_main_agent_chat_consolidates_repeated_user_preferences(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    for message in (
        "请记住：交付前必须先列出缺资料。",
        "请记住：交付前必须先说明证据不足。",
        "请记住：交付前必须先给下一步建议。",
    ):
        out = run_main_agent_chat(
            db,
            message=message,
            project_id=project.id,
            meeting_id=meeting.id,
        )

    assert out.context["memory_consolidation"]["written"] == 1
    summary = (
        db.query(Memory)
        .filter(Memory.memory_type == "memory_summary", Memory.content.contains("交付前必须先列出缺资料、证据不足和下一步"))
        .first()
    )
    assert summary is not None
    assert "memory_summary" in summary.tags

    follow_up = run_main_agent_chat(
        db,
        message="交付前我有哪些稳定偏好？",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert any("交付前必须先列出缺资料、证据不足和下一步" in item for item in follow_up.context["memories"])


def test_main_agent_chat_marks_high_impact_actions_for_approval(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="帮我退回并重新分析",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    high_impact = [action for action in out.actions if action.id in {"reject", "reanalyze"}]
    assert high_impact
    assert all(action.requires_approval for action in high_impact)


def test_main_agent_chat_persists_action_proposals(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="帮我退回并重新分析",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    proposed = [action for action in out.actions if action.requires_approval]
    assert proposed
    assert all(action.proposal_id for action in proposed)
    rows = db.query(AgentActionProposal).filter_by(project_id=project.id, meeting_id=meeting.id).all()
    assert {row.id for row in rows} == {action.proposal_id for action in proposed}
    assert all(row.status == "pending" for row in rows)


def test_main_agent_chat_asks_followup_for_ambiguous_correction(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="这条不对",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert "请说明" in out.reply
    assert "以后同类案件" in out.reply
    assert not any(action.id == "learn_rule_feedback" for action in out.actions)
    assert db.query(AgentActionProposal).filter_by(project_id=project.id, action_id="learn_rule_feedback").count() == 0


def test_main_agent_chat_proposes_user_approved_rule_learning(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="这条不对，以后观察确认单手写到场时间低置信时不能判通过，应该要求补资料。",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    learn = next(action for action in out.actions if action.id == "learn_rule_feedback")
    assert learn.requires_approval is True
    assert learn.proposal_id
    proposal = db.get(AgentActionProposal, learn.proposal_id)
    assert proposal is not None
    assert proposal.payload_json["proposal_type"] == "rule_memory_patch"
    assert proposal.payload_json["requires_evaluation"] is True
    assert proposal.payload_json["learning_patch"]["domain"] == "compliance"
    assert proposal.payload_json["learning_patch"]["scope"] == "future_similar_cases"
    assert proposal.payload_json["learning_patch"]["approval_state"] == "pending"
    assert proposal.payload_json["learning_patch"]["evaluation_gate"]["required_cases"] == [
        "A1P260307357",
        "SMS202606090070",
    ]
    assert "手写到场时间低置信时不能判通过" in proposal.payload_json["learning_patch"]["policy_text"]
    assert "手写到场时间低置信时不能判通过" in proposal.payload_json["feedback_text"]
    assert db.query(Memory).filter(Memory.content.contains("手写到场时间低置信时不能判通过")).count() == 0

    result = approve_agent_action(db, learn.proposal_id)

    assert result["ok"] is True
    assert result["status"] == "approved_pending_regression"
    assert db.query(Memory).filter(Memory.content.contains("手写到场时间低置信时不能判通过")).count() == 0
    assert db.query(LearningProposal).filter_by(project_id=project.id, status="approved_pending_regression").count() == 1


def test_main_agent_chat_governs_rule_learning_even_when_llm_is_available(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: True)
    monkeypatch.setattr(
        "app.services.agent.llm_client.chat_completion",
        lambda messages, temperature=0.2: {"role": "assistant", "content": "已加入记忆，当前该规则已生效。"},
    )

    out = run_main_agent_chat(
        db,
        message="这条不对，以后观察确认单手写到场时间低置信时不能判通过，应该要求补资料。",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.mode == "governed_feedback"
    assert "待审批" in out.reply
    assert "批准前不会改全局规则" in out.reply
    assert "已生效" not in out.reply
    assert any(action.id == "learn_rule_feedback" and action.requires_approval for action in out.actions)


def test_approve_agent_action_executes_accept_and_updates_proposal(db, chat_case, monkeypatch):
    project, meeting = chat_case
    meeting.deliverable_json = {
        "status": "pending",
        "template_quality": {"status": "pass"},
        "evidence_gate": {"blocked": False},
        "evaluation_gate": {"blocked": False},
    }
    db.add_all(
        [
            Output(
                project_id=project.id,
                meeting_id=meeting.id,
                output_type="fixed_template_excel",
                file_name="固定模板输出.xlsx",
                storage_path="/tmp/fixed-template.xlsx",
            ),
            Output(
                project_id=project.id,
                meeting_id=meeting.id,
                output_type="deliverable_package",
                file_name="A1P-CHAT.zip",
                storage_path="/tmp/A1P-CHAT.zip",
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="帮我验收通过",
        project_id=project.id,
        meeting_id=meeting.id,
    )
    accept = next(action for action in out.actions if action.id == "accept")

    result = approve_agent_action(db, accept.proposal_id)

    db.refresh(meeting)
    proposal = db.get(AgentActionProposal, accept.proposal_id)
    assert result["ok"] is True
    assert result["status"] == "accepted"
    assert meeting.status == "accepted"
    assert proposal.status == "executed"
    assert proposal.executed_at is not None


def test_main_agent_does_not_offer_acceptance_while_delivery_gate_is_blocked(db, chat_case, monkeypatch):
    project, meeting = chat_case
    monkeypatch.setattr("app.services.agent.llm_client.llm_available", lambda: False)

    out = run_main_agent_chat(
        db,
        message="帮我验收通过",
        project_id=project.id,
        meeting_id=meeting.id,
    )

    assert out.context["delivery_gate"]["blocked"] is True
    assert "验收已阻断" in out.reply
    assert not any(action.id == "accept" for action in out.actions)
