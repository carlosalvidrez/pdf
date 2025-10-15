import asyncio
from pathlib import Path
from dotenv import load_dotenv
import os

from ocr_extract import extract_text_per_page
from gpt_cleanup import process_pages
from merge_pages import merge_cleaned_pages

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
PAGES_DIR = BASE_DIR / "pages"
CLEAN_DIR = BASE_DIR / "clean"


async def main():
    # Use a dedicated OCR language setting instead of system locale LANG
    lang = os.getenv("OCR_LANG", "es")

    # Find the first input file in the input directory (prefer PDFs)
    input_candidates = sorted(INPUT_DIR.iterdir()) if INPUT_DIR.exists() else []
    selected_input = None
    for p in input_candidates:
        if p.is_file() and p.suffix.lower() == ".pdf":
            selected_input = p
            break
    # If no PDF found, fall back to the first regular file (if any)
    if selected_input is None:
        for p in input_candidates:
            if p.is_file():
                selected_input = p
                break

    if selected_input is None:
        print("⚠️ No input files found in:", INPUT_DIR)
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / f"{selected_input.stem}.text"

    # 1) Extract (comment out if you want to reuse existing 'pages')
    print("🔍 Extracting text from PDF...", selected_input.name)
    extract_text_per_page(str(selected_input), PAGES_DIR, lang=lang)

    # 2) Cleanup with GPT (parallelized with throttling)
    print("🧠 Sending pages to GPT for cleanup...")
    await process_pages(PAGES_DIR, CLEAN_DIR)

    # 3) Merge
    print("📦 Merging cleaned pages to:", output_file.name)
    merge_cleaned_pages(CLEAN_DIR, output_file)

    print("✅ Done! Cleaned text ready at:", output_file)


if __name__ == "__main__":
    asyncio.run(main())
