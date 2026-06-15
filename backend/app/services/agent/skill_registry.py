from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Set

from sqlalchemy.orm import Session

from app.models import FileRecord, ParsedDocument
from app.services.agent.tool_registry import build_tool_handlers, tool_schemas
from app.services.agent.modality_router import TEXT_INGEST_AGENT_ID, VISION_AGENT_ID, agent_modality
from app.services.domain.registry import get_sub_agent_module

SKILLS_DIR = Path(__file__).parent / "skills"

_COMMON_SUB_TOOLS = [
    "search_memory",
    "preview_file_schema",
    "get_execution_capabilities",
    "inspect_agent_domain",
]


def _agent_defs():
    return get_sub_agent_module().SUB_AGENT_DEFS


def _tool_bindings() -> Dict[str, List[str]]:
    return {agent_id: list(_COMMON_SUB_TOOLS) for agent_id in _agent_defs().keys()}

def load_skill(agent_id: str) -> str:
    if agent_id == VISION_AGENT_ID:
        path = SKILLS_DIR / "vision_agent.md"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return "视觉 Agent：使用 GLM 多模态模型读图、推理并抽取合规证据字段。"
    if agent_id == TEXT_INGEST_AGENT_ID:
        path = SKILLS_DIR / "text_ingest.md"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return "文本 Ingest：资料分拣、文档解析与实体抽取。"
    path = SKILLS_DIR / f"{agent_id}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    cfg = _agent_defs().get(agent_id, {})
    return str(cfg.get("agent_say") or "")


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
        if self.agent_id == VISION_AGENT_ID:
            modality = "vision"
        elif self.agent_id == TEXT_INGEST_AGENT_ID:
            modality = "text"
        else:
            modality = agent_modality(self.agent_id, _agent_defs().get(self.agent_id, {}))
        return {
            "id": self.agent_id,
            "name": self.name,
            "station": self.station,
            "tools": self.tool_names,
            "doc_types": sorted(self.doc_types),
            "modality": modality,
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
    cfg = _agent_defs().get(agent_id)
    if not cfg:
        raise ValueError(f"unknown sub agent: {agent_id}")
    tool_names = _tool_bindings().get(agent_id, MAIN_AGENT_TOOLS)
    return AgentRegistration(
        agent_id=agent_id,
        name=str(cfg["name"]),
        station=str(cfg["station"]),
        skill_text=load_skill(agent_id),
        tool_names=list(tool_names),
        doc_types=set(cfg.get("doc_types") or []),
    )


def register_vision_agent() -> AgentRegistration:
    return AgentRegistration(
        agent_id=VISION_AGENT_ID,
        name="视觉 Agent",
        station="视觉席",
        skill_text=load_skill(VISION_AGENT_ID),
        tool_names=[],
        doc_types=set(),
    )


def register_text_ingest_agent() -> AgentRegistration:
    return AgentRegistration(
        agent_id=TEXT_INGEST_AGENT_ID,
        name="文本 Ingest",
        station="结构化读档",
        skill_text=load_skill(TEXT_INGEST_AGENT_ID),
        tool_names=[],
        doc_types=set(),
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
    bindings = _tool_bindings()
    names = bindings.get(agent_id, MAIN_AGENT_TOOLS) if agent_id != "main" else MAIN_AGENT_TOOLS
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
    reg = register_sub_agent(agent_id) if agent_id in _agent_defs() else register_main_agent()
    doc_types = reg.doc_types

    def inspect_agent_domain() -> List[Dict[str, Any]]:
        return _inspect_domain(db, project_id, doc_types)

    handlers["inspect_agent_domain"] = lambda **_: inspect_agent_domain()
    return handlers


def list_registered_agents(
    active_ids: List[str] | None = None,
    *,
    include_vision: bool = False,
    include_text_ingest: bool = True,
) -> List[Dict[str, Any]]:
    defs = _agent_defs()
    ids = active_ids or list(defs.keys())
    agents = [register_main_agent().to_dict()]
    if include_text_ingest:
        agents.append(register_text_ingest_agent().to_dict())
    if include_vision:
        agents.append(register_vision_agent().to_dict())
    for agent_id in ids:
        if agent_id in defs:
            agents.append(register_sub_agent(agent_id).to_dict())
    return agents
