from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.exceptions import FXPGError
from app.models import FileRecord
from app.services.agent.llm_client import chat_completion, chat_json, require_agent_llm
from app.services.agent.tool_registry import build_tool_handlers, execute_tool_call, tool_schemas
from app.services.agent.sub_agents import enrich_plan_with_sub_agents
from app.services.domain.registry import get_domain_pack


def _missing_from_files(files: List[FileRecord]) -> List[str]:
    pack = get_domain_pack()
    categories = {f.document_category for f in files}
    return [d[0] for d in pack.required_docs if d[0] not in categories]


def _planner_system_prompt() -> str:
    pack = get_domain_pack()
    if pack.name == "compliance":
        return (
            "你是罗氏会议合规远程观察 Agent 的任务规划器。根据已上传观察资料，制定分析计划。"
            "必须先调用工具了解文件、预览结构、缺失资料、检索相关记忆、了解可执行能力，"
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
        if content.startswith("{"):
            plan = json.loads(content)
            plan["agent_mode"] = "agent"
            plan.setdefault("missing_documents", _missing_from_files(files))
            return enrich_plan_with_sub_agents(plan, files)

    plan = chat_json(
        messages + [{"role": "user", "content": "请直接输出最终分析计划 JSON。"}],
        schema_hint='{"steps":[],"focus_areas":[],"missing_documents":[],"priority_actions":[],"reasoning":"","agent_mode":"agent"}',
    )
    plan["agent_mode"] = "agent"
    plan.setdefault("missing_documents", _missing_from_files(files))
    return enrich_plan_with_sub_agents(plan, files)
