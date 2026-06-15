from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import FileRecord
from app.services.domain.registry import get_domain_pack


def classify_uploaded_file(
    file_name: str,
    ext: str,
    *,
    headers: Optional[List[str]] = None,
    text: str = "",
) -> Dict[str, Any]:
    pack = get_domain_pack()
    if pack.name == "compliance":
        from app.services.domain.compliance.classifier import classify_compliance_document

        return classify_compliance_document(file_name, ext, text)
    from app.services.classifier import classify_document

    return classify_document(file_name, ext, headers=headers, text=text)


def classify_file_record(f: FileRecord, text_preview: str = "") -> Dict[str, Any]:
    ext = Path(f.file_name).suffix.lower()
    return classify_uploaded_file(f.file_name, ext, text=text_preview)
