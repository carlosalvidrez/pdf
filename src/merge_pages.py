from pathlib import Path

def merge_cleaned_pages(clean_dir: Path, output_file: Path):
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as out:
        for page in sorted(clean_dir.glob("*.txt")):
            out.write(page.read_text(encoding="utf-8").strip() + "\n\n")
    print(f"📚 Merged cleaned text saved to: {output_file}")
