#!/usr/bin/env python3
"""Pre-generate all recap and quiz cache files so the app loads instantly."""

import hashlib
import json
import re
import sys
import yaml
from pathlib import Path

# Run from study_tool/ directory
sys.path.insert(0, str(Path(__file__).parent))

from config import RESOURCES_PATH, CACHE_PATH, EXAM_GUIDE_PATH, OPENAI_API_KEY, TAG_TO_EXAM
from quiz import generate_section_recap, generate_page_quiz, Question

if not OPENAI_API_KEY:
    print("[!] OPENAI_API_KEY not set. Export it or add to .env before running.")
    sys.exit(1)


def cache_file(prefix: str, *keys: str) -> Path:
    h = hashlib.md5("__".join(keys).encode()).hexdigest()
    return CACHE_PATH / f"{prefix}_{h}.json"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1])
                return meta or {}, parts[2].strip()
            except yaml.YAMLError:
                pass
    return {}, content


def split_sections(body: str) -> list[tuple[str, str]]:
    parts = re.split(r'\n(## [^\n]+)', body)
    result = []
    for i in range(1, len(parts), 2):
        heading = parts[i].lstrip('#').strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ''
        result.append((heading, content))
    return result


def should_recap(heading: str) -> bool:
    skip = {'introduction', 'lesson objectives', 'summary', 'objectives'}
    h = heading.lower()
    return not any(h == s or h.startswith(s) for s in skip)


def get_exam_objectives(tags: list, guide_text: str) -> str:
    sections = {TAG_TO_EXAM.get(tag) for tag in tags if tag in TAG_TO_EXAM}
    sections.discard(None)
    objectives = []
    for section_name in sections:
        pattern = rf'(?:Section \d+[:\s]+)?{re.escape(section_name)}.*?(?=\n##|\nSection \d|\Z)'
        match = re.search(pattern, guide_text, re.DOTALL | re.IGNORECASE)
        if match:
            objectives.append(match.group(0).strip())
    return "\n\n".join(objectives)


def main():
    guide_text = EXAM_GUIDE_PATH.read_text(encoding='utf-8') if EXAM_GUIDE_PATH.exists() else ""

    md_files = sorted(RESOURCES_PATH.rglob("*.md"))
    # Exclude the exam guide itself from lesson processing
    md_files = [f for f in md_files if f.name != "Databricks-GenAI-Exam-Guide.md"]

    print(f"Found {len(md_files)} lesson files\n")

    recap_new = recap_skipped = quiz_new = quiz_skipped = 0

    for file_path in md_files:
        file_key = str(file_path)
        content = file_path.read_text(encoding='utf-8')
        meta, body = parse_frontmatter(content)
        title = meta.get('title', file_path.stem)
        tags = meta.get('tags', [])

        print(f"📄 {file_path.relative_to(RESOURCES_PATH)}")

        # Section recaps
        sections = split_sections(body)
        for heading, section_text in sections:
            if not should_recap(heading):
                continue
            cf = cache_file("recap", file_key, heading)
            if cf.exists():
                recap_skipped += 1
                continue
            print(f"   ↳ recap: {heading[:60]}")
            recap = generate_section_recap(heading, section_text)
            cf.write_text(json.dumps({"recap": recap}))
            recap_new += 1

        # Page quiz
        cf = cache_file("quiz", file_key)
        if cf.exists():
            quiz_skipped += 1
        else:
            print(f"   ↳ quiz: generating...")
            objectives = get_exam_objectives(tags, guide_text)
            # Clean HTML tags from body before sending
            clean_body = re.sub(r'<[^>]+>', '', body)
            questions = generate_page_quiz(title, clean_body, num_questions=7, exam_objectives=objectives)
            cf.write_text(json.dumps([q.__dict__ for q in questions]))
            quiz_new += 1

        print()

    print(f"Done.")
    print(f"  Recaps  — generated: {recap_new}, skipped (cached): {recap_skipped}")
    print(f"  Quizzes — generated: {quiz_new}, skipped (cached): {quiz_skipped}")
    print(f"\nCache written to: {CACHE_PATH}")
    print("Now commit and push .cache/ to include it in the repo.")


if __name__ == "__main__":
    main()
