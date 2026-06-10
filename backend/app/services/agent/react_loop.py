from __future__ import annotations

import json
from typing import Any, Dict, List, Set

from app.config import settings
from app.services.agent.llm_client import chat_completion, require_agent_llm
from app.services.agent.pipeline_tools import PIPELINE_STEP_TOOLS, REQUIRED_FOR_FINISH, STEP_DEPENDENCIES


def _observation(executor: Any) -> Dict[str, Any]:
    return executor.get_observation()


def _system_prompt(plan: Dict[str, Any]) -> str:
    focus = "、".join(plan.get("focus_areas") or [])
    subs = "、".join(sa.get("name", "") for sa in plan.get("sub_agents") or [])
    return (
        "你是 AuditAgent 的 ReAct 编排器（外环）。内环是确定性流水线工具。\n"
        "根据当前观察，每次只选一个工具：run_step(执行一步) / get_project_state(看状态) / finish_analysis(结束)。\n"
        "必须遵守依赖：parsing 前需 classifying，extracting 前需 parsing，以此类推。\n"
        "计划重点：" + (focus or "综合") + "\n"
        "协同专员：" + (subs or "主 Agent") + "\n"
        "完成条件：至少完成 classifying→parsing→running_rules→adjudicating→generating_report，"
        "或确认某步可跳过（如无文件则直接 finish）。"
    )


def run_react_loop(executor: Any, trace: Any, max_turns: int | None = None) -> Dict[str, Any]:
    """Observe → Think → Act 循环，由 LLM 选择下一步流水线工具。"""
    require_agent_llm()
    turns = max_turns or settings.react_max_turns
    plan = executor.state.get("agent_plan") or {}
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(plan)},
        {
            "role": "user",
            "content": (
                "分析计划已就绪。请观察状态并开始调度内环工具。\n"
                f"初始状态：{json.dumps(_observation(executor), ensure_ascii=False)}"
            ),
        },
    ]

    trace.log(
        "react",
        "running",
        kind="react",
        message="ReAct 外环启动",
        detail={"mode": "react", "max_turns": turns},
    )

    completed: Set[str] = set()
    action_log: List[Dict[str, Any]] = []

    for turn in range(turns):
        msg = chat_completion(messages, tools=PIPELINE_STEP_TOOLS, temperature=0.1)

        if msg.get("tool_calls"):
            messages.append(msg)
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                name = fn["name"]
                args = json.loads(fn.get("arguments") or "{}")

                if name == "get_project_state":
                    obs = _observation(executor)
                    result = json.dumps(obs, ensure_ascii=False)
                    action_log.append({"turn": turn, "tool": name, "obs": obs})

                elif name == "run_step":
                    step = args.get("step", "")
                    reason = args.get("reason", "")
                    deps_ok = all(d in completed for d in STEP_DEPENDENCIES.get(step, []))
                    if not deps_ok:
                        result = json.dumps(
                            {"error": "dependency_not_met", "step": step, "completed": sorted(completed)},
                            ensure_ascii=False,
                        )
                    elif step in completed:
                        result = json.dumps({"skipped": True, "step": step, "message": "已完成"}, ensure_ascii=False)
                    else:
                        out = executor.execute_step(step)
                        completed.add(step)
                        result = json.dumps(out, ensure_ascii=False)
                        trace.tool(
                            step,
                            "completed",
                            message=reason,
                            detail={"react_turn": turn, **out},
                        )
                        action_log.append({"turn": turn, "tool": "run_step", "step": step, "reason": reason})

                elif name == "finish_analysis":
                    missing = REQUIRED_FOR_FINISH - completed
                    if missing and executor.state.get("file_count", 0) > 0:
                        result = json.dumps(
                            {
                                "error": "incomplete",
                                "missing_steps": sorted(missing),
                                "hint": "请继续 run_step 完成必要步骤",
                            },
                            ensure_ascii=False,
                        )
                    else:
                        summary = args.get("summary", "")
                        trace.log(
                            "react",
                            "completed",
                            kind="react",
                            message=summary or "ReAct 外环完成",
                            detail={"turns": turn + 1, "completed_steps": sorted(completed)},
                        )
                        return {
                            "completed_steps": sorted(completed),
                            "turns": turn + 1,
                            "action_log": action_log,
                            "summary": summary,
                        }
                else:
                    result = json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)

                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue

        content = (msg.get("content") or "").strip()
        if content:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": "请调用工具 run_step / get_project_state / finish_analysis 继续。",
                }
            )

    # 兜底：补跑未完成必要步骤
    for step in ["classifying", "parsing", "extracting", "running_rules", "cross_checking", "adjudicating", "generating_report"]:
        if step not in completed and executor.state.get("file_count", 0) > 0:
            if all(d in completed for d in STEP_DEPENDENCIES.get(step, [])):
                executor.execute_step(step)
                completed.add(step)

    trace.log(
        "react",
        "completed",
        kind="react",
        message="ReAct 达到轮次上限，已自动补跑",
        detail={"turns": turns, "completed_steps": sorted(completed)},
    )
    return {"completed_steps": sorted(completed), "turns": turns, "action_log": action_log, "fallback": True}
