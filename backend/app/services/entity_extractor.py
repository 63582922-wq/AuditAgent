from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.rule_engine import _standardize_row


def extract_entities_from_documents(
    project_id: str, parsed_docs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    entities: List[Dict[str, Any]] = []

    for doc in parsed_docs:
        cat = doc["document_category"]
        content = doc["content_json"]
        file_id = doc["file_id"]

        if cat in ("expense_detail", "invoice_list", "bank_statement", "trial_balance"):
            for sheet in content.get("sheets", []):
                columns_map = {
                    c["name"]: c.get("standard_field")
                    for c in sheet.get("columns", [])
                    if c.get("standard_field")
                }
                for row in sheet.get("rows", []):
                    std = _standardize_row(row["values"], columns_map)
                    _append_row_entities(entities, project_id, file_id, cat, std, row, sheet.get("sheet_name"))

        if cat == "contract":
            fields = content.get("fields") or {}
            if fields.get("contract_amount"):
                entities.append(
                    _entity(project_id, file_id, "contract_amount", fields["contract_amount"], fields, 0.95)
                )
            for key in ("party_a", "party_b", "contract_no"):
                if fields.get(key):
                    entities.append(_entity(project_id, file_id, key, str(fields[key]), fields, 0.9))

        if content.get("fields") and cat == "invoice_image":
            for key, val in content["fields"].items():
                if val not in (None, ""):
                    conf = content.get("confidence", {}).get(key, 0.75)
                    entities.append(_entity(project_id, file_id, key, val, content["fields"], conf))

    return entities


def _append_row_entities(
    entities: List[Dict],
    project_id: str,
    file_id: str,
    doc_cat: str,
    std: Dict[str, Any],
    row: Dict,
    sheet_name: Optional[str],
) -> None:
    loc = {"sheet": sheet_name, "row": row.get("row_number")}
    mapping = [
        ("amount", "amount"),
        ("invoice_number", "invoice_number"),
        ("supplier", "supplier"),
        ("customer", "customer"),
        ("date", "date"),
        ("contract_no", "contract_no"),
    ]
    for etype, key in mapping:
        val = std.get(key)
        if val not in (None, ""):
            entities.append(_entity(project_id, file_id, etype, val, {**std, **loc}, 0.92, loc))


def _entity(
    project_id: str,
    file_id: str,
    entity_type: str,
    entity_value: Any,
    source: Dict,
    confidence: float,
    location: Optional[Dict] = None,
) -> Dict:
    return {
        "project_id": project_id,
        "file_id": file_id,
        "entity_type": entity_type,
        "entity_value": str(entity_value),
        "standard_value": str(entity_value),
        "source_location": location or {},
        "confidence": confidence,
        "source_data": source,
    }
