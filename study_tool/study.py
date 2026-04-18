#!/usr/bin/env python3
"""Databricks GenAI Exam Study Tool - Main CLI."""

import json
import os
import random
from pathlib import Path
from config import CONTENT_FILE, EXAM_SECTIONS
from quiz import generate_quiz, generate_mixed_quiz, run_quiz


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def load_content() -> dict:
    """Load parsed content from JSON."""
    if not CONTENT_FILE.exists():
        print("\n  [!] Content file not found. Run parse_content.py first.")
        print(f"      Expected: {CONTENT_FILE}")
        return None

    return json.loads(CONTENT_FILE.read_text())


def print_header(text: str):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def print_subheader(text: str):
    """Print a subsection header."""
    print(f"\n{'-' * 60}")
    print(f"  {text}")
    print(f"{'-' * 60}")


def truncate_text(text: str, max_lines: int = 50) -> str:
    """Truncate text to max lines for display."""
    lines = text.split('\n')
    if len(lines) <= max_lines:
        return text
    return '\n'.join(lines[:max_lines]) + f"\n\n  ... [{len(lines) - max_lines} more lines]"


def display_topic(topic: dict, show_full: bool = False):
    """Display a topic's content."""
    print_subheader(f"{topic['title']}")

    print(f"\n  Type: {topic['type'].capitalize()}")
    if topic.get('course'):
        print(f"  Course: {topic['course']}")
    if topic.get('module'):
        print(f"  Module: {topic['module']}")

    # Key concepts
    concepts = topic.get('key_concepts', [])
    if concepts:
        print("\n  KEY CONCEPTS:")
        for c in concepts[:10]:
            print(f"    * {c}")

    # Content
    content = topic.get('markdown_content', '')
    if content:
        print("\n  CONTENT:")
        print("-" * 60)
        display_content = content if show_full else truncate_text(content, 40)
        # Indent content for readability
        for line in display_content.split('\n'):
            print(f"  {line}")
        print("-" * 60)

    # Code examples
    code_examples = topic.get('code_examples', [])
    if code_examples:
        print("\n  CODE EXAMPLES:")
        for i, code in enumerate(code_examples[:3], 1):
            print(f"\n  Example {i}:")
            print("  ```")
            truncated = truncate_text(code, 15)
            for line in truncated.split('\n'):
                print(f"  {line}")
            print("  ```")


def study_by_section(content: dict):
    """Study mode organized by exam section."""
    by_section = content.get('by_exam_section', {})

    while True:
        clear_screen()
        print_header("STUDY BY EXAM SECTION")

        print("\n  Select a section to study:\n")
        section_ids = list(EXAM_SECTIONS.keys())

        for i, section_id in enumerate(section_ids, 1):
            section = EXAM_SECTIONS[section_id]
            topic_count = len(by_section.get(section_id, []))
            print(f"  {i}. {section['name']} ({section['weight']}) - {topic_count} topics")

        print(f"\n  b. Back to main menu")

        choice = input("\n  Enter choice: ").strip().lower()

        if choice == 'b':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(section_ids):
                section_id = section_ids[idx]
                topics = by_section.get(section_id, [])
                browse_topics(topics, EXAM_SECTIONS[section_id]['name'])
        except ValueError:
            pass


def browse_topics(topics: list, section_name: str):
    """Browse through a list of topics."""
    if not topics:
        print("\n  No topics found in this section.")
        input("  Press Enter to continue...")
        return

    current = 0

    while True:
        clear_screen()
        print_header(f"{section_name} - Topic {current + 1} of {len(topics)}")

        display_topic(topics[current])

        print(f"\n  Navigation:")
        print(f"  [n]ext  [p]rev  [f]ull content  [q]uiz this topic  [b]ack")

        choice = input("\n  Enter choice: ").strip().lower()

        if choice == 'n':
            current = (current + 1) % len(topics)
        elif choice == 'p':
            current = (current - 1) % len(topics)
        elif choice == 'f':
            clear_screen()
            print_header(f"{section_name} - Full Content")
            display_topic(topics[current], show_full=True)
            input("\n  Press Enter to continue...")
        elif choice == 'q':
            quiz_topic(topics[current])
        elif choice == 'b':
            return


def quiz_topic(topic: dict):
    """Generate and run a quiz for a specific topic."""
    clear_screen()
    print_header(f"QUIZ: {topic['title']}")

    num_q = input("\n  How many questions? (3-10, default 5): ").strip()
    try:
        num_q = int(num_q)
        num_q = max(3, min(10, num_q))
    except ValueError:
        num_q = 5

    print(f"\n  Generating {num_q} questions...")
    questions = generate_quiz(topic, num_q)

    if questions:
        run_quiz(questions)
    else:
        print("\n  Could not generate questions.")

    input("\n  Press Enter to continue...")


def quiz_menu(content: dict):
    """Quiz mode menu."""
    by_section = content.get('by_exam_section', {})
    all_content = content.get('all_content', [])

    while True:
        clear_screen()
        print_header("QUIZ MODE")

        print("""
  Quiz Options:

  1. Quiz on specific exam section
  2. Quick 5-question random quiz
  3. Full 10-question practice exam
  4. Back to main menu
""")

        choice = input("  Enter choice: ").strip()

        if choice == '1':
            # Select section
            print("\n  Select exam section:\n")
            section_ids = list(EXAM_SECTIONS.keys())
            for i, section_id in enumerate(section_ids, 1):
                section = EXAM_SECTIONS[section_id]
                print(f"  {i}. {section['name']}")

            sec_choice = input("\n  Enter choice: ").strip()
            try:
                idx = int(sec_choice) - 1
                if 0 <= idx < len(section_ids):
                    section_id = section_ids[idx]
                    topics = by_section.get(section_id, [])
                    if topics:
                        # Pick random topics from section
                        sample = random.sample(topics, min(3, len(topics)))
                        print(f"\n  Generating quiz for {EXAM_SECTIONS[section_id]['name']}...")
                        questions = generate_mixed_quiz(sample, 5)
                        if questions:
                            run_quiz(questions)
                        input("\n  Press Enter to continue...")
            except ValueError:
                pass

        elif choice == '2':
            # Quick random quiz
            if all_content:
                sample = random.sample(all_content, min(5, len(all_content)))
                print("\n  Generating quick quiz...")
                questions = generate_mixed_quiz(sample, 5)
                if questions:
                    run_quiz(questions)
                input("\n  Press Enter to continue...")

        elif choice == '3':
            # Full practice exam
            if all_content:
                sample = random.sample(all_content, min(10, len(all_content)))
                print("\n  Generating practice exam (10 questions)...")
                questions = generate_mixed_quiz(sample, 10)
                if questions:
                    run_quiz(questions)
                input("\n  Press Enter to continue...")

        elif choice == '4':
            return


def quick_review(content: dict):
    """Quick review of key concepts by section."""
    by_section = content.get('by_exam_section', {})

    clear_screen()
    print_header("QUICK REVIEW - KEY CONCEPTS")

    for section_id, section in EXAM_SECTIONS.items():
        topics = by_section.get(section_id, [])
        all_concepts = []
        for t in topics:
            all_concepts.extend(t.get('key_concepts', []))

        # Dedupe and limit
        unique_concepts = list(dict.fromkeys(all_concepts))[:15]

        print(f"\n  {section['name']} ({section['weight']}):")
        print(f"  {'-' * 50}")
        for c in unique_concepts:
            print(f"    * {c}")

    input("\n  Press Enter to return to main menu...")


def main_menu(content: dict):
    """Main menu loop."""
    while True:
        clear_screen()
        print_header("DATABRICKS GENAI EXAM STUDY TOOL")

        metadata = content.get('metadata', {})
        print(f"\n  Loaded: {metadata.get('total_items', 0)} topics")
        print(f"  ({metadata.get('notebook_count', 0)} from notebooks, {metadata.get('notes_count', 0)} from notes)")

        print("""
  Main Menu:

  1. Study by Exam Section
  2. Take a Quiz
  3. Quick Review (Key Concepts)
  4. Exit
""")

        choice = input("  Enter choice (1-4): ").strip()

        if choice == '1':
            study_by_section(content)
        elif choice == '2':
            quiz_menu(content)
        elif choice == '3':
            quick_review(content)
        elif choice == '4':
            print("\n  Good luck on your exam!")
            break


def main():
    """Entry point."""
    content = load_content()
    if content:
        main_menu(content)
    else:
        print("\n  To get started:")
        print("  1. cd study_tool")
        print("  2. python parse_content.py")
        print("  3. export OPENAI_API_KEY='your-key'")
        print("  4. python study.py")


if __name__ == "__main__":
    main()
