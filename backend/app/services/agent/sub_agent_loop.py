from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.llm_client import chat_completion, chat_json, require_agent_llm
from app.services.agent.mcp_hub import McpHub
from app.services.agent.mission_planner import MissionTask
from app.services.agent.pipeline_executor import PipelineExecutor

BRIEF_SCHEMA = (
    '{"summary":"","findings":[],"focus_risks":[],"confidence":0.85,"tools_used":[]}'
)


def _default_brief(task: MissionTask, step_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "agent_id": task.assignee,
        "task_id": task.id,
        "title": task.title,
        "summary": f"{task.assignee_name} 已完成 {task.title}",
        "findings": [task.objective] if task.objective else [],
        "focus_risks": [],
        "confidence": 0.7,
        "tools_used": [],
        "step_results": step_results,
    }


def _run_tool_phase(
    hub: McpHub,
    messages: List[Dict[str, Any]],
    trace: AgentTrace,
    agent_id: str,
    max_turns: int,
) -> List[str]:
    tools_used: List[str] = []
    schemas = hub.tool_schemas()
    if not schemas:
        return tools_used

    for turn in range(max_turns):
        msg = chat_completion(messages, tools=schemas, temperature=0.1)
        if not msg.get("tool_calls"):
            if msg.get("content"):
                messages.append({"role": "assistant", "content": msg["content"]})
            break

        messages.append(msg)
        for tc in msg["tool_calls"]:
            fn = tc["function"]
            name = fn["name"]
            result = hub.call_tool(name, fn.get("arguments") or "{}")
            tools_used.append(name)
            trace.tool(
                name,
                "completed",
                message=f"子 Agent {agent_id} 调用",
                detail={"agent_id": agent_id, "turn": turn, "mcp": name.startswith("mcp_")},
            )
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    return tools_used


def _summarize_brief(
    task: MissionTask,
    skill_text: str,
    tools_used: List[str],
    step_results: List[Dict[str, Any]],
    tool_transcript: str,
) -> Dict[str, Any]:
    prompt = (
        f"你是{task.assignee_name}。Skill：\n{skill_text[:800]}\n\n"
        f"任务：{task.title}\n目标：{task.objective}\n\n"
        f"工具调查记录：\n{tool_transcript[:3000]}\n\n"
        f"流水线执行结果：\n{json.dumps(step_results, ensure_ascii=False)[:2000]}\n\n"
        "请输出 JSON 专员简报：summary(80字内), findings(数组), focus_risks(数组), "
        "confidence(0-1), tools_used(数组)。"
    )
    data = chat_json([{"role": "user", "content": prompt}], schema_hint=BRIEF_SCHEMA)
    data.setdefault("tools_used", tools_used)
    data["agent_id"] = task.assignee
    data["task_id"] = task.id
    data["title"] = task.title
    data["step_results"] = step_results
    return data


def run_sub_agent_session(
    db: Session,
    project_id: str,
    task: MissionTask,
    skill_text: str,
    executor: PipelineExecutor,
    trace: AgentTrace,
) -> Dict[str, Any]:
    """子 Agent：MCP 工具调查 → 流水线步骤 → 专员简报。"""
    files = executor.state.get("files") or []

    if not settings.enable_sub_agent_llm:
        step_results: List[Dict[str, Any]] = []
        for step in task.pipeline_steps:
            if step not in executor.state["completed_steps"]:
                step_results.append(executor.execute_step(step))
        brief = _default_brief(task, step_results)
        trace.log(
            "sub_agent",
            "completed",
            kind="sub_agent",
            name=task.assignee_name,
            message=brief["summary"],
            detail={"brief": brief, "llm": False},
        )
        return brief

    require_agent_llm()
    hub = McpHub.for_agent(db, project_id, task.assignee, files)

    ingest_done = "extracting" in (executor.state.get("completed_steps") or set())
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                f"{skill_text}\n\n"
                f"当前任务：{task.title}\n目标：{task.objective}\n"
                "请先调用工具了解资料与记忆，不要编造数据。"
                + ("资料已结构化，可调用 inspect_agent_domain。" if ingest_done else "资料尚未抽取，优先 preview/search。")
            ),
        },
        {
            "role": "user",
            "content": (
                f"可用工具：{', '.join(hub.list_tool_names())}\n"
                f"MCP 服务：{json.dumps(hub.server_summary(), ensure_ascii=False)}\n"
                "请开始调查。"
            ),
        },
    ]

    trace.log(
        "sub_agent",
        "running",
        kind="sub_agent",
        name=task.assignee_name,
        message=f"工具调查：{task.title}",
        detail={"tools": hub.list_tool_names(), "mcp_servers": hub.server_summary()},
    )

    tools_used = _run_tool_phase(
        hub,
        messages,
        trace,
        task.assignee,
        settings.sub_agent_max_tool_turns,
    )

    step_results: List[Dict[str, Any]] = []
    for step in task.pipeline_steps:
        if step not in executor.state["completed_steps"]:
            step_results.append(executor.execute_step(step))

    transcript_parts = [
        m["content"] for m in messages if m.get("role") in ("assistant", "tool") and m.get("content")
    ]
    transcript = "\n".join(str(p)[:500] for p in transcript_parts)

    brief = _summarize_brief(task, skill_text, tools_used, step_results, transcript)
    trace.log(
        "sub_agent",
        "completed",
        kind="sub_agent",
        name=task.assignee_name,
        message=brief.get("summary", task.title),
        detail={"brief": brief},
    )
    return brief


def run_main_synthesis_brief(
    executor: PipelineExecutor,
    trace: AgentTrace,
    task: MissionTask,
) -> Dict[str, Any]:
    """主 Agent 汇总各子 Agent 简报，供综合研判使用。"""
    briefs: Dict[str, Any] = executor.state.get("sub_agent_briefs") or {}
    if not briefs:
        return {"summary": "无子 Agent 简报", "findings": []}

    if not settings.enable_sub_agent_llm:
        summary = "；".join(b.get("summary", "") for b in briefs.values() if b.get("summary"))
        return {"summary": summary or "子 Agent 已完成分工", "sub_briefs": list(briefs.keys())}

    require_agent_llm()
    prompt = (
        f"你是主 Agent，即将执行「{task.title}」。\n"
        f"各子 Agent 简报：\n{json.dumps(briefs, ensure_ascii=False)[:4000]}\n"
        '输出 JSON：{"summary":"","priority_findings":[],"coordination_notes":""}'
    )
    synthesis = chat_json(
        [{"role": "user", "content": prompt}],
        schema_hint='{"summary":"","priority_findings":[],"coordination_notes":""}',
    )
    trace.log(
        "orchestrator",
        "completed",
        kind="main_agent",
        name="主 Agent",
        message=synthesis.get("summary", "已汇总子 Agent 结论"),
        detail={"synthesis": synthesis},
    )
    return synthesis
