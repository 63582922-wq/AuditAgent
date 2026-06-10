from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from sqlalchemy.orm import Session

from app.models import FileRecord
from app.services.constants import REQUIRED_DOCS
from app.services.memory_rag import format_memories_for_prompt, retrieve_memories
from app.services.parsers.excel_parser import parse_excel


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
        {
            "type": "function",
            "function": {
                "name": "preview_file_schema",
                "description": "预览文件结构（表头、行数、字段），不跑全量解析",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_name": {"type": "string", "description": "文件名，可选；不传则预览全部"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_execution_capabilities",
                "description": "获取系统可执行的流水线步骤与交叉比对能力说明",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]


def execution_capabilities() -> Dict[str, Any]:
    return {
        "pipeline_steps": [
            "classifying",
            "parsing",
            "extracting",
            "running_rules",
            "cross_checking",
            "adjudicating",
            "generating_report",
        ],
        "cross_check_modules": [
            "amounts",
            "duplicates",
            "three_way",
            "anomalies",
            "cross_period",
            "record_links",
        ],
        "rule_categories": [
            "expense_detail",
            "invoice_list",
            "bank_statement",
            "trial_balance",
            "contract",
            "tax_return",
            "payroll",
            "social_security",
        ],
    }


def _preview_one_file(f: FileRecord) -> Dict[str, Any]:
    ext = Path(f.file_name).suffix.lower()
    out: Dict[str, Any] = {
        "file_name": f.file_name,
        "document_category": f.document_category,
        "confidence": f.confidence,
    }
    path = Path(f.storage_path)
    if ext in (".xlsx", ".xls", ".csv") and path.exists():
        try:
            content = parse_excel(path)
            sheets = content.get("sheets") or []
            out["sheet_count"] = len(sheets)
            if sheets:
                out["headers"] = [c.get("name") for c in sheets[0].get("columns", [])][:20]
                out["row_count"] = len(sheets[0].get("rows", []))
        except Exception as exc:
            out["preview_error"] = str(exc)
    elif ext in (".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"):
        out["note"] = "非表格文件，将在 parsing 阶段全文/OCR 解析"
    return out


def build_tool_handlers(
    db: Session,
    files_summary: List[Dict[str, Any]],
    file_records: List[FileRecord] | None = None,
) -> Dict[str, Callable]:
    records = file_records or []

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

    def preview_file_schema(file_name: str = "") -> List[Dict[str, Any]]:
        targets = records
        if file_name:
            targets = [r for r in records if r.file_name == file_name]
        return [_preview_one_file(r) for r in targets]

    def get_execution_capabilities() -> Dict[str, Any]:
        return execution_capabilities()

    return {
        "list_uploaded_files": lambda **_: list_uploaded_files(),
        "get_required_documents": lambda **_: get_required_documents(),
        "search_memory": lambda query, risk_category="": search_memory(query, risk_category),
        "preview_file_schema": lambda file_name="": preview_file_schema(file_name),
        "get_execution_capabilities": lambda **_: get_execution_capabilities(),
    }


def execute_tool_call(name: str, arguments: str, handlers: Dict[str, Callable]) -> str:
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
