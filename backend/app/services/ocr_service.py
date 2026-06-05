"""Unified OCR: GLM-4.6V 视觉模型优先，Tesseract 兜底。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Tuple

from PIL import Image


def ocr_pil_image(img: Image.Image, lang: str = "chi_sim+eng") -> Tuple[str, str]:
    from app.services.vision_client import vision_analyze_pil_image, vision_available, vision_fields_to_text

    if vision_available():
        try:
            data = vision_analyze_pil_image(img)
            text = vision_fields_to_text(data)
            if text.strip():
                return text.strip(), f"vision:{data.get('_model', 'glm')}"
        except Exception:
            pass

    try:
        import pytesseract

        text = pytesseract.image_to_string(img, lang=lang)
        return text.strip(), "tesseract"
    except Exception:
        return "", "none"


def ocr_image_file(file_path: Path) -> Tuple[str, str]:
    from app.services.vision_client import (
        normalize_vision_fields,
        vision_analyze_image,
        vision_available,
        vision_fields_to_text,
    )

    if vision_available():
        try:
            data = vision_analyze_image(file_path)
            text = vision_fields_to_text(data)
            if text.strip():
                return text.strip(), "vision:glm"
        except Exception:
            pass

    img = Image.open(file_path).convert("RGB")
    return ocr_pil_image(img)


def ocr_scanned_pdf(file_path: Path, max_pages: int = 10) -> Tuple[str, str, List[dict]]:
    import fitz

    from app.services.vision_client import vision_available

    texts: List[str] = []
    pages_meta: List[dict] = []
    engine = "none"
    use_vision = vision_available()
    page_limit = min(max_pages, 5 if use_vision else max_pages)

    with fitz.open(file_path) as doc:
        for i, page in enumerate(doc):
            if i >= page_limit:
                break
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text, eng = ocr_pil_image(img)
            if eng != "none":
                engine = eng
            texts.append(text)
            pages_meta.append({"page_number": i + 1, "text": text, "ocr_engine": eng})

    return "\n".join(texts), engine, pages_meta
