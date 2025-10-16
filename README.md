# text-cleanup-pipeline

OCR + GPT cleanup pipeline for long PDFs. Splits pages, extracts text (or OCR),
sends each page to an OpenAI model for correction, then merges the results.

## Requirements
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) for package management
- OpenAI API key

## Quick Start

```bash
# 1) Get the project
# (You likely downloaded the zip from ChatGPT; otherwise clone/extract it)

# 2) Install deps
uv sync

# 3) Configure environment
cp .env.example .env
# edit .env and set OPENAI_API_KEY, LANG, etc.

# 4) Place your PDF
cp /path/to/your.pdf input/mybook.pdf

# 5) Run the pipeline
uv run
```

Output will be written to `output/book_cleaned.txt`.

## Notes
- OCR modes:
  - `OCR_MODE=auto` (default): use embedded text if available; otherwise local EasyOCR.
  - `OCR_MODE=local`: force local OCR when needed.
  - `OCR_MODE=llm`: perform OCR with the LLM using rendered page images. The CURRENT page is sent along with PREVIOUS and NEXT page images as context to improve accuracy. Only the CURRENT page text is returned.
  - To pick the model for LLM OCR, set `OCR_LLM_MODEL` (defaults to `LLM_MODEL` or `gpt-4o-mini`).
- The pipeline always splits the source PDF into single-page PDFs under `pages/pdfs/` (one PDF per page).
- Concurrency (parallel page cleanup) is controlled by `MAX_CONCURRENCY` in `.env`.
- The cleanup LLM used is controlled by `LLM_MODEL` in `.env`.
- You can rerun without re-extracting by commenting the extraction step in `src/main.py`.
