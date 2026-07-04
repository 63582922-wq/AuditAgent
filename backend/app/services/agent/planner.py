from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.exceptions import FXPGError
from app.models import FileRecord
from app.services.agent.llm_client import chat_completion, chat_json, parse_llm_json, require_agent_llm
from app.services.agent.tool_registry import build_tool_handlers, execute_tool_call, tool_schemas
from app.services.agent.sub_agents import enrich_plan_with_sub_agents
from app.services.cross_checker import check_missing_documents
from app.services.domain.compliance.case_loader import bootstrap_meeting_profile
from app.services.domain.registry import get_domain_pack


def _missing_from_files(db: Session, project_id: str, files: List[FileRecord]) -> List[dict]:
    pack = get_domain_pack()
    categories = {f.document_category for f in files}
    if pack.name == "compliance":
        meeting_id = next((f.meeting_id for f in files if f.meeting_id), None)
        meeting_case = bootstrap_meeting_profile(db, project_id, meeting_id)
        return check_missing_documents(categories, domain="compliance", meeting_case=meeting_case)
    return [
        {"document_type": doc_type, "importance": importance, "reason": reason}
        for doc_type, importance, reason in pack.required_docs
        if doc_type not in categories
    ]


def _meeting_case_from_files(db: Session, project_id: str, files: List[FileRecord]) -> dict[str, Any]:
    meeting_id = next((f.meeting_id for f in files if f.meeting_id), None)
    return bootstrap_meeting_profile(db, project_id, meeting_id)


def _is_sms_meeting_case(meeting_case: dict[str, Any]) -> bool:
    code = str(meeting_case.get("meeting_code") or meeting_case.get("会议编码") or "").upper()
    return code.startswith("SMS")


def _plan_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " ".join(_plan_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_plan_text(item) for item in value.values())
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _a1_missing_claim(value: Any) -> bool:
    text = _plan_text(value).upper()
    return "A1" in text and any(token in text for token in ("缺", "HAS_A1", "A1_MEETING_EXPORT", "严重", "最高风险"))


def _strip_a1_missing_sentences(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[。；;\n])", text)
    kept = [part.strip() for part in parts if part.strip() and not _a1_missing_claim(part)]
    return "".join(kept).strip()


def _filter_sms_a1_items(items: Any, fallback: str) -> list[Any]:
    if not isinstance(items, list):
        items = [items] if items else []
    filtered = [item for item in items if not _a1_missing_claim(item)]
    if fallback not in [_plan_text(item) for item in filtered]:
        filtered.append(fallback)
    return filtered


def _normalize_plan_for_context(
    db: Session,
    project_id: str,
    files: List[FileRecord],
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply deterministic domain constraints after LLM planning.

    The LLM may retrieve stale memories or generic required-doc guidance. Those
    are useful hints, but current meeting profile and rule-engine missing-doc
    logic must be authoritative.
    """
    pack = get_domain_pack()
    normalized = dict(plan)
    if pack.name != "compliance":
        return normalized

    meeting_case = _meeting_case_from_files(db, project_id, files)
    normalized["missing_documents"] = _missing_from_files(db, project_id, files)

    if not _is_sms_meeting_case(meeting_case):
        return normalized

    normalized["focus_areas"] = _filter_sms_a1_items(
        normalized.get("focus_areas"),
        "SMS远程观察替代证据链核对",
    )
    normalized["priority_actions"] = _filter_sms_a1_items(
        normalized.get("priority_actions"),
        "按SMS远程观察口径核对直播观看数据、确认单、ZOOM/直播截图与沟通记录",
    )
    reasoning = _strip_a1_missing_sentences(str(normalized.get("reasoning") or ""))
    sms_note = "SMS远程观察不要求A1导出，应以直播观看数据、确认单、ZOOM/直播截图与沟通记录构建替代证据链。"
    normalized["reasoning"] = f"{reasoning} {sms_note}".strip() if reasoning else sms_note
    return normalized


def _planner_system_prompt() -> str:
    pack = get_domain_pack()
    if pack.name == "compliance":
        return (
        "你是罗氏会议合规远程观察 Agent 的任务规划器。根据已上传观察资料，制定分析计划。"
        "必须先调用工具了解文件、预览结构、缺失资料、检索相关记忆、了解可执行能力，"
        "长期记忆只能作为线索，不得覆盖当前资料、会议编码和缺件规则。"
        "会议编码以 SMS 开头的远程观察案件不要求 A1 会议导出，"
        "应以直播观看数据、确认单、ZOOM/直播截图、沟通短信和邮件构建替代证据链。"
        "再输出 JSON 计划。steps 数组请从 "
        "classify/parse/extract/run_rules/cross_check/adjudicate/report 中选择。"
        )
    return (
        "你是会计风险评估 Agent 的任务规划器。根据已上传资料，制定分析计划。"
        "必须先调用工具了解文件、预览结构、缺失资料、检索相关记忆、了解可执行能力，"
        "再输出 JSON 计划。steps 数组请从 "
        "classify/parse/extract/run_rules/cross_check/adjudicate/report 中选择。"
    )


def plan_analysis(db: Session, project_id: str, files: List[FileRecord]) -> Dict[str, Any]:
    """Planner：LLM + 工具调用生成分析计划（纯智能体，无回退）。"""
    require_agent_llm()

    files_summary = [
        {
            "file_name": f.file_name,
            "document_category": f.document_category,
            "confidence": f.confidence,
        }
        for f in files
    ]
    handlers = build_tool_handlers(db, files_summary, file_records=files)
    tools = tool_schemas()
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": _planner_system_prompt(),
        },
        {
            "role": "user",
            "content": (
                f"项目 ID: {project_id}\n"
                f"已上传文件概要: {json.dumps(files_summary, ensure_ascii=False)}\n"
                "请调用必要工具，然后给出分析计划 JSON，字段："
                "steps(数组), focus_areas(数组), missing_documents(数组), "
                "priority_actions(数组), reasoning(字符串), sub_agents(可选数组), agent_mode 固定为 agent"
            ),
        },
    ]

    for _ in range(4):
        msg = chat_completion(messages, tools=tools)
        if msg.get("tool_calls"):
            messages.append(msg)
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                result = execute_tool_call(fn["name"], fn.get("arguments") or "{}", handlers)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue

        content = (msg.get("content") or "").strip()
        if content:
            try:
                plan = parse_llm_json(content)
                plan["agent_mode"] = "agent"
                plan = _normalize_plan_for_context(db, project_id, files, plan)
                return enrich_plan_with_sub_agents(plan, files)
            except (json.JSONDecodeError, ValueError):
                pass

    plan = chat_json(
        messages + [{"role": "user", "content": "请直接输出最终分析计划 JSON。"}],
        schema_hint='{"steps":[],"focus_areas":[],"missing_documents":[],"priority_actions":[],"reasoning":"","agent_mode":"agent"}',
    )
    plan["agent_mode"] = "agent"
    plan = _normalize_plan_for_context(db, project_id, files, plan)
    return enrich_plan_with_sub_agents(plan, files)
