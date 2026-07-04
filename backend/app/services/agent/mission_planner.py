from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import FileRecord
from app.services.agent.llm_client import chat_json, require_agent_llm
from app.services.agent.planner import plan_analysis
from app.services.agent.skill_registry import list_registered_agents, load_skill
from app.services.agent.sub_agents import route_sub_agents
from app.services.agent.modality_router import VISION_AGENT_ID, split_files_by_modality, TEXT_INGEST_AGENT_ID
from app.services.domain.registry import get_domain_pack

INGEST_TEXT_STEPS = ["parsing", "extracting"]
VISION_STEPS = ["vision_parsing"]
RULES_STEPS = ["running_rules"]
CROSS_STEPS = ["cross_checking"]
SYNTHESIS_STEPS = ["adjudicating", "generating_report"]

RULES_AGENTS = ("invoice", "tax", "ledger")
CROSS_AGENTS = ("treasury", "contract")
COMPLIANCE_RULES_AGENTS = ("speaker", "policy", "meeting_plan")
COMPLIANCE_CROSS_AGENTS = ("attendance", "evidence")


@dataclass
class MissionTask:
    id: str
    title: str
    assignee: str
    assignee_name: str
    pipeline_steps: List[str]
    objective: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissionPlan:
    objective: str
    reasoning: str
    tasks: List[MissionTask]
    agent_plan: Dict[str, Any] = field(default_factory=dict)
    sub_agents: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "reasoning": self.reasoning,
            "tasks": [t.to_dict() for t in self.tasks],
            "sub_agents": self.sub_agents,
            "agent_plan": self.agent_plan,
            "registered_agents": list_registered_agents(
                [sa["id"] for sa in self.sub_agents],
                include_vision=any(t.assignee == VISION_AGENT_ID for t in self.tasks),
                include_text_ingest=any(t.assignee == TEXT_INGEST_AGENT_ID for t in self.tasks),
            ),
        }


def _pick_assignee(sub_agents: List[Dict[str, Any]], candidates: tuple[str, ...]) -> Dict[str, Any] | None:
    ids = {sa["id"] for sa in sub_agents}
    for agent_id in candidates:
        if agent_id in ids:
            return next(sa for sa in sub_agents if sa["id"] == agent_id)
    return None


def _plan_items_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return "、".join(part for part in (_plan_items_text(item) for item in value) if part)
    if isinstance(value, dict):
        return "、".join(part for part in (_plan_items_text(item) for item in value.values()) if part)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def build_default_mission(files: List[FileRecord], agent_plan: Dict[str, Any]) -> MissionPlan:
    pack = get_domain_pack()
    sub_agents = agent_plan.get("sub_agents") or route_sub_agents(files, agent_plan)
    _, vision_files = split_files_by_modality(files)
    focus = _plan_items_text(agent_plan.get("focus_areas")) or "、".join(pack.planner_focus)
    reasoning = agent_plan.get("reasoning") or (
        f"主 Agent（DeepSeek）拆解任务与汇总交付；"
        f"{'视觉 Agent（GLM）处理图片，' if vision_files else ''}"
        f"文本 Ingest 负责分拣与文档解析；调度 {len(sub_agents) or 1} 路子 Agent。"
    )
    rules_agents = COMPLIANCE_RULES_AGENTS if pack.name == "compliance" else RULES_AGENTS
    cross_agents = COMPLIANCE_CROSS_AGENTS if pack.name == "compliance" else CROSS_AGENTS

    tasks: List[MissionTask] = [
        MissionTask(
            id="classify",
            title="文本 Ingest · 资料分拣",
            assignee=TEXT_INGEST_AGENT_ID,
            assignee_name="文本 Ingest",
            pipeline_steps=["classifying"],
            objective="识别资料类型，为视觉/文本解析分派做准备",
        ),
    ]

    if vision_files:
        tasks.append(
            MissionTask(
                id="vision_ingest",
                title="视觉 Agent · 读图推理",
                assignee=VISION_AGENT_ID,
                assignee_name="视觉 Agent",
                pipeline_steps=list(VISION_STEPS),
                objective=f"GLM 视觉模型读图并推理（{len(vision_files)} 张），抽取合规证据字段",
            )
        )

    tasks.append(
        MissionTask(
            id="text_ingest",
            title="文本 Ingest · 文档解析",
            assignee=TEXT_INGEST_AGENT_ID,
            assignee_name="文本 Ingest",
            pipeline_steps=list(INGEST_TEXT_STEPS),
            objective="解析 Excel/PDF/Word 资料（含 PPT-PDF 混合页）并抽取实体",
        )
    )

    rules_agent = _pick_assignee(sub_agents, rules_agents)
    if rules_agent:
        rules_objective = (
            "对照讲者时长、材料编码与 A1 计划执行合规规则扫描"
            if pack.name == "compliance"
            else "对票据、费用与账务类资料执行规则引擎扫描"
        )
        tasks.append(
            MissionTask(
                id="rules",
                title=f"{rules_agent['name']} · 规则扫描",
                assignee=rules_agent["id"],
                assignee_name=rules_agent["name"],
                pipeline_steps=list(RULES_STEPS),
                objective=rules_objective,
            )
        )
    else:
        tasks.append(
            MissionTask(
                id="rules",
                title="规则扫描",
                assignee="main",
                assignee_name="主 Agent",
                pipeline_steps=list(RULES_STEPS),
                objective="执行规则引擎扫描",
            )
        )

    cross_agent = _pick_assignee(sub_agents, cross_agents)
    if cross_agent:
        cross_objective = (
            "核对签到、远程沟通与证据链完整性"
            if pack.name == "compliance"
            else "银行流水、合同与票据之间的勾稽与异常检测"
        )
        tasks.append(
            MissionTask(
                id="cross",
                title=f"{cross_agent['name']} · 交叉比对",
                assignee=cross_agent["id"],
                assignee_name=cross_agent["name"],
                pipeline_steps=list(CROSS_STEPS),
                objective=cross_objective,
            )
        )
    else:
        tasks.append(
            MissionTask(
                id="cross",
                title="交叉比对与勾稽",
                assignee="main",
                assignee_name="主 Agent",
                pipeline_steps=list(CROSS_STEPS),
                objective="执行交叉比对模块",
            )
        )

    tasks.append(
        MissionTask(
            id="synthesis",
            title="综合研判与交付",
            assignee="main",
            assignee_name="主 Agent",
            pipeline_steps=list(SYNTHESIS_STEPS),
            objective="汇总各子 Agent 结论，生成 Finding PDF/Excel 交付物",
        )
    )

    objective = (
        f"完成「{focus}」方向的会议合规观察与 Finding 交付"
        if pack.name == "compliance"
        else f"完成「{focus}」方向的财务风险评估与交付"
    )
    return MissionPlan(
        objective=objective,
        reasoning=reasoning,
        tasks=tasks,
        agent_plan=agent_plan,
        sub_agents=sub_agents,
    )


def _apply_deliverable_feedback(plan: Dict[str, Any]) -> Dict[str, Any]:
    feedback = plan.get("deliverable_feedback") or ""
    if feedback:
        plan = dict(plan)
        prefix = f"用户验收退回：{feedback}。"
        plan["reasoning"] = prefix + (plan.get("reasoning") or "")
        actions = list(plan.get("priority_actions") or [])
        actions.insert(0, f"针对退回意见调整分析：{feedback}")
        plan["priority_actions"] = actions
    return plan


def _maybe_enhance_with_llm(mission: MissionPlan) -> MissionPlan:
    """可选：LLM 润色任务标题与目标，失败则保留默认拆解。"""
    try:
        require_agent_llm()
        task_brief = [
            {"id": t.id, "title": t.title, "assignee": t.assignee_name, "objective": t.objective}
            for t in mission.tasks
        ]
        enhanced = chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是主 Agent 任务编排器。根据已有任务列表，仅优化 title 与 objective 字段，"
                        "不改变 assignee 与步骤顺序。输出 JSON："
                        '{"tasks":[{"id":"","title":"","objective":""}]}'
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"objective": mission.objective, "tasks": task_brief},
                        ensure_ascii=False,
                    ),
                },
            ],
            schema_hint='{"tasks":[{"id":"","title":"","objective":""}]}',
        )
        by_id = {item["id"]: item for item in enhanced.get("tasks") or []}
        for task in mission.tasks:
            patch = by_id.get(task.id)
            if not patch:
                continue
            if patch.get("title"):
                task.title = patch["title"]
            if patch.get("objective"):
                task.objective = patch["objective"]
    except Exception:
        pass
    return mission


def decompose_mission(
    db: Session,
    project_id: str,
    files: List[FileRecord],
    agent_plan: Optional[Dict[str, Any]] = None,
    *,
    use_llm_enhance: bool = True,
) -> MissionPlan:
    """主 Agent：Planner 计划 + 任务拆解 + 子 Agent 委派。"""
    plan = agent_plan or plan_analysis(db, project_id, files)
    plan = _apply_deliverable_feedback(plan)
    mission = build_default_mission(files, plan)
    if use_llm_enhance:
        mission = _maybe_enhance_with_llm(mission)
    return mission
