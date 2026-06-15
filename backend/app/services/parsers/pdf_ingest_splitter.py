from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import fitz
import pdfplumber
from PIL import Image

from app.config import settings

RetryCallback = Callable[[int, int, float, str], None]

MIN_PAGE_TEXT_CHARS = 80
MIN_EMBED_PIXELS = 10_000
MIN_EMBED_AREA_RATIO = 0.05
VISION_PAGE_DPI = 200
MAX_VISION_PAGES = 20


@dataclass
class VisionSliceWork:
    page_number: int
    ingest_mode: str
    slice_id: str
    image: Image.Image
    embed_index: Optional[int] = None


@dataclass
class PdfIngestResult:
    file_type: str = "pdf"
    pdf_type: str = "text"
    ingest_mode: str = "text"
    ocr_engine: str = "none"
    text_content: str = ""
    pages: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    vision_slices: List[Dict[str, Any]] = field(default_factory=list)

    def to_content_json(self) -> Dict[str, Any]:
        return {
            "file_type": self.file_type,
            "pdf_type": self.pdf_type,
            "ingest_mode": self.ingest_mode,
            "ocr_engine": self.ocr_engine,
            "text_content": self.text_content,
            "pages": self.pages,
            "tables": self.tables,
            "vision_slices": self.vision_slices,
        }


def _page_text(page: fitz.Page) -> str:
    return (page.get_text("text") or "").strip()


def _render_page(page: fitz.Page, dpi: int = VISION_PAGE_DPI) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def _extract_embedded_images(
    doc: fitz.Document,
    page: fitz.Page,
    page_number: int,
    *,
    min_area_ratio: float = MIN_EMBED_AREA_RATIO,
    min_pixels: int = MIN_EMBED_PIXELS,
    min_dimension: int = 0,
) -> List[Tuple[Image.Image, int]]:
    page_area = max(page.rect.width * page.rect.height, 1.0)
    out: List[Tuple[Image.Image, int]] = []
    seen_xrefs: set[int] = set()

    for embed_index, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        try:
            base = doc.extract_image(xref)
            if not base or not base.get("image"):
                continue
            pil = Image.open(io.BytesIO(base["image"])).convert("RGB")
            w, h = pil.size
            if w * h < min_pixels:
                continue
            if min_dimension and min(w, h) < min_dimension:
                continue
            rects = page.get_image_rects(xref)
            if rects:
                img_area = sum(r.width * r.height for r in rects)
                if img_area / page_area < min_area_ratio:
                    continue
            out.append((pil, embed_index))
        except Exception:
            continue
    return out


def _classify_page(page: fitz.Page, doc: fitz.Document, page_number: int) -> Tuple[str, List[VisionSliceWork]]:
    text = _page_text(page)
    text_len = len(text)
    embed_ratio = 0.12 if text_len >= MIN_PAGE_TEXT_CHARS else MIN_EMBED_AREA_RATIO
    embed_kwargs = (
        {"min_area_ratio": embed_ratio, "min_pixels": 40_000, "min_dimension": 180}
        if text_len >= MIN_PAGE_TEXT_CHARS
        else {}
    )
    embeds = _extract_embedded_images(doc, page, page_number, **embed_kwargs)
    work: List[VisionSliceWork] = []

    if text_len < MIN_PAGE_TEXT_CHARS:
        work.append(
            VisionSliceWork(
                page_number=page_number,
                ingest_mode="vision_page",
                slice_id=f"p{page_number}-page",
                image=_render_page(page),
            )
        )
        return "vision_page", work

    for embed_index, (pil, _) in embeds:
        work.append(
            VisionSliceWork(
                page_number=page_number,
                ingest_mode="vision_embed",
                slice_id=f"p{page_number}-embed-{embed_index}",
                image=pil,
                embed_index=embed_index,
            )
        )

    if work:
        return "hybrid", work
    return "text_only", work


def _extract_text_pages(file_path: Path) -> Tuple[List[Dict[str, Any]], str, List[Dict[str, Any]]]:
    text_chunks: List[str] = []
    pages_out: List[Dict[str, Any]] = []

    with fitz.open(file_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = _page_text(page)
            text_chunks.append(text)
            blocks = []
            for block in page.get_text("blocks"):
                if len(block) >= 5 and str(block[4]).strip():
                    blocks.append(
                        {
                            "text": str(block[4]).strip(),
                            "bbox": [block[0], block[1], block[2], block[3]],
                        }
                    )
            pages_out.append({"page_number": i, "text": text, "blocks": blocks})

    full_text = "\n".join(text_chunks)
    tables: List[Dict[str, Any]] = []
    if len(full_text.strip()) > MIN_PAGE_TEXT_CHARS:
        with pdfplumber.open(file_path) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables() or []:
                    tables.append({"page_number": page_no, "rows": table})

    return pages_out, full_text, tables


def _analyze_slice_compliance(
    image: Image.Image,
    document_category: str,
    file_name: str,
    *,
    page_number: int,
    ingest_mode: str,
    slice_id: str,
    on_retry: Optional[RetryCallback] = None,
) -> Dict[str, Any]:
    from app.services.domain.compliance.compliance_vision import analyze_compliance_pil_image

    label = f"{file_name}#p{page_number}"
    content = analyze_compliance_pil_image(
        image,
        document_category,
        label,
        on_retry=on_retry,
    )
    content["source_file_name"] = file_name
    content["page_number"] = page_number
    content["ingest_mode"] = ingest_mode
    content["slice_id"] = slice_id
    return content


def _analyze_slice_financial(
    image: Image.Image,
    document_category: str,
    file_name: str,
    *,
    page_number: int,
    ingest_mode: str,
    slice_id: str,
) -> Dict[str, Any]:
    from app.services.ocr_service import ocr_pil_image

    text, engine = ocr_pil_image(image)
    return {
        "file_type": "image",
        "document_type": document_category,
        "ocr_engine": engine,
        "text_content": text,
        "fields": {},
        "confidence": {},
        "bbox": [],
        "vision_agent": True,
        "source_file_name": file_name,
        "page_number": page_number,
        "ingest_mode": ingest_mode,
        "slice_id": slice_id,
    }


def ingest_pdf_hybrid(
    file_path: Path,
    document_category: str,
    file_name: str = "",
    *,
    domain: str = "compliance",
    on_retry: Optional[RetryCallback] = None,
    analyze_vision: bool = True,
) -> PdfIngestResult:
    """PDF 混合 ingest：文本层 + 薄页/内嵌图走视觉 Agent 结构化解析。"""
    file_name = file_name or file_path.name
    pages_out, full_text, tables = _extract_text_pages(file_path)

    vision_work: List[VisionSliceWork] = []
    page_modes: List[str] = []

    with fitz.open(file_path) as doc:
        page_limit = min(len(doc), MAX_VISION_PAGES)
        for i in range(page_limit):
            page = doc[i]
            mode, work = _classify_page(page, doc, i + 1)
            page_modes.append(mode)
            vision_work.extend(work)

    has_vision = bool(vision_work)
    text_rich = len(full_text.strip()) > MIN_PAGE_TEXT_CHARS

    if has_vision and text_rich:
        pdf_type = ingest_mode = "hybrid"
    elif has_vision:
        pdf_type = "scanned"
        ingest_mode = "vision_only" if not text_rich else "hybrid"
    else:
        pdf_type = "text"
        ingest_mode = "text"

    vision_slices: List[Dict[str, Any]] = []
    ocr_engine = "none"
    delay_sec = max(settings.vision_inter_request_delay_sec, 0.0)
    made_request = False

    if analyze_vision and vision_work:
        for item in vision_work:
            if made_request and delay_sec > 0:
                time.sleep(delay_sec)
            made_request = True

            if domain == "compliance":
                sl_content = _analyze_slice_compliance(
                    item.image,
                    document_category,
                    file_name,
                    page_number=item.page_number,
                    ingest_mode=item.ingest_mode,
                    slice_id=item.slice_id,
                    on_retry=on_retry,
                )
            else:
                sl_content = _analyze_slice_financial(
                    item.image,
                    document_category,
                    file_name,
                    page_number=item.page_number,
                    ingest_mode=item.ingest_mode,
                    slice_id=item.slice_id,
                )

            engine = sl_content.get("ocr_engine") or "vision"
            if engine != "none":
                ocr_engine = engine

            vision_text = sl_content.get("text_content") or ""
            if vision_text and ingest_mode == "vision_only":
                full_text = f"{full_text}\n{vision_text}".strip() if full_text.strip() else vision_text
            elif vision_text and item.ingest_mode == "vision_page":
                full_text = f"{full_text}\n{vision_text}".strip()

            vision_slices.append(
                {
                    "slice_id": item.slice_id,
                    "page_number": item.page_number,
                    "ingest_mode": item.ingest_mode,
                    "embed_index": item.embed_index,
                    "document_category": document_category,
                    "content_json": sl_content,
                }
            )

    return PdfIngestResult(
        pdf_type=pdf_type,
        ingest_mode=ingest_mode,
        ocr_engine=ocr_engine,
        text_content=full_text,
        pages=pages_out,
        tables=tables,
        vision_slices=vision_slices,
    )
