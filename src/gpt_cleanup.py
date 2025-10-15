import asyncio
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tqdm import tqdm

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set. Please configure your .env file.")

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "6"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))

client = AsyncOpenAI(api_key=API_KEY)

SYSTEM_PROMPT = (
    "You are an expert OCR text corrector. Correct misspellings, diacritics, "
    "and punctuation errors based on context. Preserve paragraph structure, language, "
    "and meaning. Do not invent new content; only fix recognition errors. Return only the cleaned text."
)


async def _call_gpt(messages) -> str:
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        # max_tokens=MAX_OUTPUT_TOKENS,
    )
    return resp.choices[0].message.content.strip()


async def _retry_gpt(messages, retries: int = 5, base_delay: float = 1.5) -> str:
    for attempt in range(retries):
        try:
            return await _call_gpt(messages)
        except Exception as e:
            if attempt == retries - 1:
                raise
            # Exponential backoff with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            print(f"⚠️ GPT call failed (attempt {attempt + 1}/{retries}): {e}. Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)
    # unreachable
    return ""


async def _process_one(page_file: Path, prev_text: str, next_text: str, clean_dir: Path, sem: asyncio.Semaphore):
    async with sem:
        raw_text = page_file.read_text(encoding="utf-8")
        user_content = (
            "Use the surrounding pages only as context to better correct OCR errors in the CURRENT page.\n"
            "Do not copy or rephrase content from context pages into the output.\n\n"
            "=== PREVIOUS PAGE (context only) ===\n" + (prev_text or "") + "\n\n"
            "=== CURRENT PAGE (to clean) ===\n" + raw_text + "\n\n"
            "=== NEXT PAGE (context only) ===\n" + (next_text or "") + "\n\n"
            "Return only the cleaned text for the CURRENT page."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        cleaned = await _retry_gpt(messages)
        (clean_dir / page_file.name).write_text(cleaned, encoding="utf-8")


async def process_pages(raw_dir: Path, clean_dir: Path):
    clean_dir.mkdir(exist_ok=True)
    page_files = sorted(raw_dir.glob("*.txt"))
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    # Preload all texts to avoid repeated disk IO under semaphore
    texts = [p.read_text(encoding="utf-8") for p in page_files]

    tasks = []
    for i, p in enumerate(page_files):
        prev_text = texts[i - 1] if i - 1 >= 0 else ""
        next_text = texts[i + 1] if i + 1 < len(texts) else ""
        tasks.append(_process_one(p, prev_text, next_text, clean_dir, sem))

    # Manual progress bar for asyncio
    pbar = tqdm(total=len(tasks), desc="Cleaning pages", unit="page")

    async def _wrap(task):
        try:
            await task
        finally:
            pbar.update(1)

    await asyncio.gather(*[_wrap(t) for t in tasks])
    pbar.close()
