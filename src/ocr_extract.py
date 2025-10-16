import base64
import io
import os
from pathlib import Path

import fitz  # PyMuPDF
import easyocr
from openai import OpenAI


def _save_page_pdf(doc: fitz.Document, page_index: int, pdfs_dir: Path):
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    single = fitz.open()
    single.insert_pdf(doc, from_page=page_index, to_page=page_index)
    out_path = pdfs_dir / f"page_{page_index + 1:03}.pdf"
    single.save(out_path)
    single.close()
    return out_path


def _render_page_png(page: fitz.Page, dpi: int = 200) -> bytes:
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")


def _b64_image_part(png_bytes: bytes):
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{base64.b64encode(png_bytes).decode()}"
        },
    }


def _llm_ocr_page(client: OpenAI, model: str, prev_png: bytes | None, cur_png: bytes, next_png: bytes | None) -> str:
    content = [
        {"type": "text", "text": (
            "Transcribe the text from the CURRENT page image. Use the PREVIOUS and NEXT page images only as context\n"
            "to resolve broken words or lines across page boundaries. Return only the text that visually appears on\n"
            "the CURRENT page. Preserve original language, accents, and punctuation; do not summarize or invent content."
        )}
    ]
    if prev_png:
        content.append({"type": "text", "text": "=== PREVIOUS PAGE (context only) ==="})
        content.append(_b64_image_part(prev_png))
    content.append({"type": "text", "text": "=== CURRENT PAGE (to transcribe) ==="})
    content.append(_b64_image_part(cur_png))
    if next_png:
        content.append({"type": "text", "text": "=== NEXT PAGE (context only) ==="})
        content.append(_b64_image_part(next_png))

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a meticulous OCR transcriber for document page images."},
            {"role": "user", "content": content},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def extract_text_per_page(pdf_path: str, output_dir: Path, lang: str = "es", mode: str = "auto"):
    """Extract text from each PDF page.
    Behavior by mode:
    - auto: use embedded text layer when present; otherwise local EasyOCR.
    - local: force local OCR (EasyOCR) when no embedded text.
    - llm: perform OCR via LLM using rendered page images with prev/next context.

    Always writes one .txt per page to output_dir and also splits the PDF
    into per-page PDFs under output_dir / "pdfs".
    """
    doc = fitz.open(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdfs_dir = output_dir / "pdfs"

    use_llm = mode.lower() == "llm"
    use_local_only = mode.lower() == "local"

    # Prepare local OCR reader if needed
    reader = None
    if use_local_only or (not use_llm):
        try:
            reader = easyocr.Reader([lang], gpu=False)
        except Exception:
            reader = None

    # Setup LLM client if needed
    llm_client = None
    llm_model = os.getenv("OCR_LLM_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    if use_llm:
        llm_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    total = len(doc)
    # Pre-render all PNGs if using LLM for fast neighbor access
    rendered = [None] * total if use_llm else None

    for i, page in enumerate(doc, start=1):
        # Always save per-page PDF
        _save_page_pdf(doc, i - 1, pdfs_dir)

        page_text = page.get_text("text") or ""
        text = page_text.strip()

        do_llm = use_llm
        if not do_llm:
            # auto/local path: prefer embedded text when present
            if text:
                pass  # keep embedded text
            else:
                # No embedded text -> OCR
                if reader is None:
                    # Lazy-init reader if not yet created
                    try:
                        reader = easyocr.Reader([lang], gpu=False)
                    except Exception:
                        reader = None
                if reader is not None:
                    png_bytes = _render_page_png(page, dpi=200)
                    img_path = output_dir / f"page_{i:03}.png"
                    # Keep temporary image only if needed (we'll remove it below)
                    Path(img_path).write_bytes(png_bytes)
                    ocr_result = reader.readtext(str(img_path), detail=0)
                    text = "\n".join(ocr_result).strip()
                    try:
                        Path(img_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                else:
                    # As a fallback when EasyOCR is unavailable, use LLM OCR
                    do_llm = True

        if do_llm:
            # Render current and neighbor pages
            if rendered is not None and rendered[i - 1] is None:
                rendered[i - 1] = _render_page_png(page, dpi=200)
            cur_png = rendered[i - 1] if rendered is not None else _render_page_png(page, dpi=200)
            prev_png = None
            next_png = None
            if i - 2 >= 0:
                if rendered is not None and rendered[i - 2] is None:
                    rendered[i - 2] = _render_page_png(doc[i - 2], dpi=200)
                prev_png = rendered[i - 2] if rendered is not None else _render_page_png(doc[i - 2], dpi=200)
            if i < total:
                if rendered is not None and rendered[i] is None:
                    rendered[i] = _render_page_png(doc[i], dpi=200)
                next_png = rendered[i] if rendered is not None else _render_page_png(doc[i], dpi=200)

            text = _llm_ocr_page(llm_client, llm_model, prev_png, cur_png, next_png)

        (output_dir / f"page_{i:03}.txt").write_text(text, encoding="utf-8")
        print(f"✅ Extracted page {i}/{len(doc)}")

    doc.close()
