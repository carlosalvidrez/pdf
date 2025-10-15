import fitz  # PyMuPDF
import easyocr
from pathlib import Path

def extract_text_per_page(pdf_path: str, output_dir: Path, lang: str = "es"):
    """Extract text from each PDF page.
    Fallback to OCR with EasyOCR when the embedded text layer is empty.
    Writes one .txt per page to output_dir.
    """
    doc = fitz.open(pdf_path)
    reader = easyocr.Reader([lang], gpu=False)
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if not text.strip():
            # OCR fallback
            pix = page.get_pixmap(dpi=200)
            img_path = output_dir / f"page_{i:03}.png"
            pix.save(img_path)
            ocr_result = reader.readtext(str(img_path), detail=0)
            text = "\n".join(ocr_result)
            try:
                img_path.unlink(missing_ok=True)
            except Exception:
                pass

        (output_dir / f"page_{i:03}.txt").write_text(text, encoding="utf-8")
        print(f"✅ Extracted page {i}/{len(doc)}")

    doc.close()
