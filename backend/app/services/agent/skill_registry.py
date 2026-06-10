from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Set

from sqlalchemy.orm import Session

from app.models import FileRecord, ParsedDocument
from app.services.agent.sub_agents import SUB_AGENT_DEFS
from app.services.agent.tool_registry import build_tool_handlers, tool_schemas

SKILLS_DIR = Path(__file__).parent / "skills"


def load_skill(agent_id: str) -> str:
    path = SKILLS_DIR / f"{agent_id}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    cfg = SUB_AGENT_DEFS.get(agent_id, {})
    return str(cfg.get("agent_say") or "")


# 各子 Agent 可使用的 Planner 工具 + 领域 inspect 工具
SUB_AGENT_TOOL_BINDINGS: Dict[str, List[str]] = {
    "tax": ["search_memory", "preview_file_schema", "get_execution_capabilities", "inspect_agent_domain"],
    "invoice": ["search_memory", "preview_file_schema", "get_execution_capabilities", "inspect_agent_domain"],
    "contract": ["search_memory", "preview_file_schema", "get_execution_capabilities", "inspect_agent_domain"],
    "treasury": ["search_memory", "preview_file_schema", "get_execution_capabilities", "inspect_agent_domain"],
    "ledger": ["search_memory", "preview_file_schema", "get_execution_capabilities", "inspect_agent_domain"],
}

MAIN_AGENT_TOOLS = [
    "list_uploaded_files",
    "get_required_documents",
    "search_memory",
    "preview_file_schema",
    "get_execution_capabilities",
]


@dataclass
class AgentRegistration:
    agent_id: str
    name: str
    station: str
    skill_text: str
    tool_names: List[str] = field(default_factory=list)
    doc_types: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.agent_id,
            "name": self.name,
            "station": self.station,
            "tools": self.tool_names,
            "doc_types": sorted(self.doc_types),
            "skill_preview": self.skill_text[:200],
        }


_INSPECT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "inspect_agent_domain",
        "description": "查看本子 Agent 负责的资料类型已解析摘要（表头、行数、关键字段）",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def _schema_by_name(name: str) -> Dict[str, Any] | None:
    if name == "inspect_agent_domain":
        return _INSPECT_TOOL_SCHEMA
    for schema in tool_schemas():
        if schema["function"]["name"] == name:
            return schema
    return None


def register_sub_agent(agent_id: str) -> AgentRegistration:
    cfg = SUB_AGENT_DEFS.get(agent_id)
    if not cfg:
        raise ValueError(f"unknown sub agent: {agent_id}")
    tool_names = SUB_AGENT_TOOL_BINDINGS.get(agent_id, MAIN_AGENT_TOOLS)
    return AgentRegistration(
        agent_id=agent_id,
        name=str(cfg["name"]),
        station=str(cfg["station"]),
        skill_text=load_skill(agent_id),
        tool_names=list(tool_names),
        doc_types=set(cfg.get("doc_types") or []),
    )


def register_main_agent() -> AgentRegistration:
    return AgentRegistration(
        agent_id="main",
        name="主 Agent",
        station="指挥席",
        skill_text="负责任务拆解、调度子 Agent、综合研判与交付。",
        tool_names=list(MAIN_AGENT_TOOLS),
        doc_types=set(),
    )


def get_tools_for_agent(agent_id: str) -> List[Dict[str, Any]]:
    """MCP 风格：返回某 Agent 可用的工具 schema 列表。"""
    names = SUB_AGENT_TOOL_BINDINGS.get(agent_id, MAIN_AGENT_TOOLS) if agent_id != "main" else MAIN_AGENT_TOOLS
    schemas: List[Dict[str, Any]] = []
    for name in names:
        schema = _schema_by_name(name)
        if schema:
            schemas.append(schema)
    return schemas


def _inspect_domain(db: Session, project_id: str, doc_types: Set[str]) -> List[Dict[str, Any]]:
    rows = (
        db.query(ParsedDocument, FileRecord)
        .join(FileRecord, ParsedDocument.file_id == FileRecord.id)
        .filter(ParsedDocument.project_id == project_id)
        .all()
    )
    out: List[Dict[str, Any]] = []
    for pd, fr in rows:
        if doc_types and fr.document_category not in doc_types:
            continue
        content = pd.content_json or {}
        sheets = content.get("sheets") or []
        summary: Dict[str, Any] = {
            "file_name": fr.file_name,
            "document_category": fr.document_category,
        }
        if sheets:
            summary["sheet_count"] = len(sheets)
            summary["headers"] = [c.get("name") for c in sheets[0].get("columns", [])][:15]
            summary["row_count"] = len(sheets[0].get("rows", []))
        elif content.get("fields"):
            summary["fields"] = list((content.get("fields") or {}).keys())[:15]
        elif content.get("text_content"):
            summary["text_preview"] = str(content.get("text_content", ""))[:300]
        out.append(summary)
    return out


def build_agent_handlers(
    agent_id: str,
    db: Session,
    project_id: str,
    file_records: List[FileRecord],
) -> Dict[str, Callable]:
    """为子 Agent 构建工具 handler（含领域 inspect）。"""
    files_summary = [
        {
            "file_name": f.file_name,
            "document_category": f.document_category,
            "confidence": f.confidence,
        }
        for f in file_records
    ]
    handlers = build_tool_handlers(db, files_summary, file_records=file_records)
    reg = register_sub_agent(agent_id) if agent_id in SUB_AGENT_DEFS else register_main_agent()
    doc_types = reg.doc_types

    def inspect_agent_domain() -> List[Dict[str, Any]]:
        return _inspect_domain(db, project_id, doc_types)

    handlers["inspect_agent_domain"] = lambda **_: inspect_agent_domain()
    return handlers


def list_registered_agents(active_ids: List[str] | None = None) -> List[Dict[str, Any]]:
    ids = active_ids or list(SUB_AGENT_DEFS.keys())
    agents = [register_main_agent().to_dict()]
    for agent_id in ids:
        if agent_id in SUB_AGENT_DEFS:
            agents.append(register_sub_agent(agent_id).to_dict())
    return agents
