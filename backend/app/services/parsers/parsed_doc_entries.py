from __future__ import annotations

from typing import Any, Dict, List


def expand_parsed_doc_entries(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """一份 PDF 混合 ingest 可展开为多条逻辑 parsed_doc（文本轨 + 各 vision 切片）。"""
    content = doc.get("content_json") or {}
    vision_slices = content.get("vision_slices") or []
    if not vision_slices:
        return [doc]

    entries: List[Dict[str, Any]] = []
    ingest_mode = str(content.get("ingest_mode") or "text")
    has_text = bool((content.get("text_content") or "").strip() or content.get("pages"))

    if has_text and ingest_mode != "vision_only":
        entries.append(
            {
                **doc,
                "ingest_mode": "text" if ingest_mode == "hybrid" else ingest_mode,
                "page_number": None,
                "slice_id": None,
            }
        )

    for sl in vision_slices:
        sl_content = sl.get("content_json") or {}
        entries.append(
            {
                "file_id": doc["file_id"],
                "file_name": doc.get("file_name"),
                "document_category": sl.get("document_category") or doc.get("document_category"),
                "page_number": sl.get("page_number"),
                "slice_id": sl.get("slice_id"),
                "ingest_mode": sl.get("ingest_mode"),
                "content_json": sl_content,
                "text_content": sl_content.get("text_content") or "",
            }
        )

    return entries if entries else [doc]


def flatten_parsed_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for doc in docs:
        out.extend(expand_parsed_doc_entries(doc))
    return out
