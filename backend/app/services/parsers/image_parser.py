from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.ocr_service import ocr_image_file


def parse_image(file_path: Path) -> dict[str, Any]:
    text, ocr_engine = ocr_image_file(file_path)

    fields: dict[str, Any] = {}
    if ocr_engine.startswith("vision"):
        from app.services.vision_client import normalize_vision_fields, vision_analyze_image, vision_available

        if vision_available():
            try:
                fields = normalize_vision_fields(vision_analyze_image(file_path))
            except Exception:
                fields = _extract_invoice_fields(text)
    else:
        fields = _extract_invoice_fields(text)

    confidence = {k: (0.9 if v else 0.0) for k, v in fields.items()}
    if ocr_engine == "none":
        confidence = {k: 0.0 for k in confidence}

    return {
        "file_type": "image",
        "document_type": "invoice_image" if fields.get("invoice_number") else "unknown_image",
        "ocr_engine": ocr_engine,
        "text_content": text,
        "fields": fields,
        "confidence": confidence,
        "bbox": [],
    }


def _extract_invoice_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    patterns = {
        "invoice_number": r"发票号码[:：]?\s*(\d+)",
        "invoice_date": r"开票日期[:：]?\s*(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})",
        "buyer_name": r"购买方[:：].*?名\s*称[:：]?\s*(.+?)(?:\n|纳税人)",
        "seller_name": r"销售方[:：].*?名\s*称[:：]?\s*(.+?)(?:\n|纳税人)",
        "total_amount": r"价税合计.*?([\d,\.]+)",
        "tax_amount": r"税额.*?([\d,\.]+)",
        "tax_rate": r"税率.*?([\d\.]+%?)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.S)
        if m:
            val = m.group(1).strip()
            if key in {"total_amount", "tax_amount"}:
                try:
                    val = float(val.replace(",", ""))
                except ValueError:
                    pass
            fields[key] = val
    return fields


def annotate_image(source: Path, annotations: list[dict], output: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(img)
    for ann in annotations:
        bbox = ann.get("bbox")
        if bbox and len(bbox) == 4:
            draw.rectangle(bbox, outline="red", width=3)
        text = ann.get("text", "")
        if bbox:
            draw.text((bbox[0], max(bbox[1] - 20, 0)), text[:80], fill="red")
    img.save(output)
