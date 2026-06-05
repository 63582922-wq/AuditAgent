from __future__ import annotations

from typing import Any, Callable, Dict, List

from sqlalchemy.orm import Session

from app.services.constants import REQUIRED_DOCS
from app.services.memory_rag import format_memories_for_prompt, retrieve_memories


def tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_uploaded_files",
                "description": "列出当前项目已上传文件及初步分类",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_required_documents",
                "description": "获取完整风险评估所需的资料清单及重要性",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_memory",
                "description": "检索长期记忆中的会计口径、政策与历史案例",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "检索问题"},
                        "risk_category": {"type": "string", "description": "风险类别，可选"},
                    },
                    "required": ["query"],
                },
            },
        },
    ]


def build_tool_handlers(db: Session, files_summary: List[Dict[str, Any]]) -> Dict[str, Callable]:
    def list_uploaded_files() -> List[Dict[str, Any]]:
        return files_summary

    def get_required_documents() -> List[Dict[str, str]]:
        return [{"document_type": d[0], "importance": d[1], "reason": d[2]} for d in REQUIRED_DOCS]

    def search_memory(query: str, risk_category: str = "") -> str:
        mems = retrieve_memories(
            db,
            risk_category=risk_category or None,
            query_text=query,
            limit=5,
        )
        return format_memories_for_prompt(mems)

    return {
        "list_uploaded_files": lambda **_: list_uploaded_files(),
        "get_required_documents": lambda **_: get_required_documents(),
        "search_memory": lambda query, risk_category="": search_memory(query, risk_category),
    }


def execute_tool_call(name: str, arguments: str, handlers: Dict[str, Callable]) -> str:
    import json

    fn = handlers.get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
    try:
        args = json.loads(arguments) if arguments else {}
        result = fn(**args)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
