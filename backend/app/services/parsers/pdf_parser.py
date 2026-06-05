from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
import pdfplumber

from app.services.ocr_service import ocr_scanned_pdf


def parse_pdf(file_path: Path) -> dict[str, Any]:
    text_chunks: list[str] = []
    pages_out: list[dict[str, Any]] = []

    with fitz.open(file_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            text_chunks.append(text)
            blocks = []
            for block in page.get_text("blocks"):
                if len(block) >= 5 and block[4].strip():
                    blocks.append(
                        {
                            "text": block[4].strip(),
                            "bbox": [block[0], block[1], block[2], block[3]],
                        }
                    )
            pages_out.append({"page_number": i, "text": text, "blocks": blocks})

    full_text = "\n".join(text_chunks)
    pdf_type = "text" if len(full_text.strip()) > 80 else "scanned"
    ocr_engine = "none"

    if pdf_type == "scanned":
        ocr_text, ocr_engine, ocr_pages = ocr_scanned_pdf(file_path)
        if ocr_text.strip():
            full_text = ocr_text
            for i, p in enumerate(ocr_pages):
                if i < len(pages_out):
                    pages_out[i]["text"] = p.get("text", "")
                    pages_out[i]["ocr_engine"] = p.get("ocr_engine", ocr_engine)

    tables: list[dict[str, Any]] = []
    if pdf_type == "text" or len(full_text.strip()) > 80:
        with pdfplumber.open(file_path) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables() or []:
                    tables.append({"page_number": page_no, "rows": table})

    return {
        "file_type": "pdf",
        "pdf_type": pdf_type,
        "ocr_engine": ocr_engine,
        "pages": pages_out,
        "tables": tables,
        "text_content": full_text,
    }


def extract_contract_fields(content: dict[str, Any]) -> dict[str, Any]:
    text = content.get("text_content", "")
    fields: dict[str, Any] = {}
    import re

    patterns = {
        "contract_no": r"合同编号[:：]?\s*([A-Za-z0-9\-]+)",
        "party_a": r"甲方[:：]?\s*(.+?)(?:\n|乙方)",
        "party_b": r"乙方[:：]?\s*(.+?)(?:\n|签订|合同金额)",
        "contract_amount": r"合同金额[:：]?\s*([\d,\.]+)",
        "tax_rate": r"税率[:：]?\s*([\d\.]+%?)",
        "invoice_type": r"(增值税专用发票|增值税普通发票)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.S)
        if m:
            val = m.group(1).strip()
            if key == "contract_amount":
                try:
                    val = float(val.replace(",", ""))
                except ValueError:
                    pass
            fields[key] = val
    return fields
