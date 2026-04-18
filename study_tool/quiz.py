"""Quiz generation using OpenAI API."""

import re
from dataclasses import dataclass
from config import OPENAI_API_KEY, OPENAI_MODEL

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


@dataclass
class Question:
    """A quiz question."""
    objective: str
    question: str
    options: dict  # {"A": "...", "B": "...", ...}
    answer: str
    explanation: str


QUIZ_SYSTEM_PROMPT = """You are a helpful study assistant for Databricks Generative AI concepts.

Generate questions that help learners understand and remember key concepts. Mix question types:
- Conceptual: "What is the purpose of..." or "Why would you use..."
- Practical: "When building a RAG application, which approach..."
- Comparison: "What is the difference between..."
- Best practices: "Which is recommended when..."

Format each question as:
OBJECTIVE: [What concept this tests]
Q: [Clear question text]
A) [Option]
B) [Option]
C) [Option]
D) [Option]
ANSWER: [Correct letter]
EXPLANATION: [Why this answer is correct, and what makes the other options incorrect or less suitable]

---

Focus on helping the learner truly understand:
- Databricks tools: Vector Search, MLflow, Unity Catalog, Model Serving, Agent Framework
- GenAI concepts: RAG, embeddings, chunking, guardrails, evaluation, agents
- When and why to use different approaches

Make explanations educational - they're the most valuable part for learning.
"""

PAGE_QUIZ_PROMPT = """You are a study assistant helping a learner review key concepts from a lesson.

Generate quick review questions that test understanding of the main points. Focus on:
- Key takeaways and important concepts
- Practical understanding (not trivia)
- Clear, direct questions

Format each question as:
Q: [Clear question]
A) [Option]
B) [Option]
C) [Option]
D) [Option]
ANSWER: [Letter]
EXPLANATION: [Brief explanation of why this is correct]

---
"""


def generate_quiz(topic: dict, num_questions: int = 5) -> list[Question]:
    """Generate quiz questions for a topic using OpenAI."""
    if not HAS_OPENAI:
        print("\n  [!] OpenAI library not installed. Run: pip install openai")
        return []

    if not OPENAI_API_KEY:
        print("\n  [!] OPENAI_API_KEY not set. Export it in your environment.")
        return []

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Use frontmatter data
    title = topic.get('title', 'Unknown')
    summary = topic.get('summary', '')
    sections = topic.get('sections', [])
    tags = topic.get('tags', [])
    body = topic.get('body', '')[:1500]  # Limit content for API

    prompt = f"""Generate {num_questions} questions on: {title}

SUMMARY: {summary}

SECTIONS: {', '.join(sections) if sections else 'N/A'}

TAGS: {', '.join(tags) if tags else 'N/A'}

CONTENT EXCERPT:
{body}

Generate {num_questions} scenario-based questions with 4 options each.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1800  # Reduced for speed
        )

        result = parse_quiz_response(response.choices[0].message.content)
        if not result:
            print(f"[!] Parsing failed. Raw response:\n{response.choices[0].message.content[:500]}")
        return result

    except Exception as e:
        import traceback
        print(f"\n  [!] Error generating quiz: {e}")
        traceback.print_exc()
        return []


def generate_page_quiz(title: str, content: str, num_questions: int = 3) -> list[Question]:
    """Generate quick review questions for a single page of content."""
    if not HAS_OPENAI:
        print("\n  [!] OpenAI library not installed. Run: pip install openai")
        return []

    if not OPENAI_API_KEY:
        print("\n  [!] OPENAI_API_KEY not set. Export it in your environment.")
        return []

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Limit content length for speed
    content = content[:3000]

    prompt = f"""Generate {num_questions} quick review questions for this lesson.

LESSON: {title}

CONTENT:
{content}

Generate {num_questions} questions testing the key concepts from this specific lesson.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": PAGE_QUIZ_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1200
        )

        result = parse_quiz_response(response.choices[0].message.content)
        if not result:
            print(f"[!] Parsing failed. Raw response:\n{response.choices[0].message.content[:500]}")
        return result

    except Exception as e:
        import traceback
        print(f"\n  [!] Error generating page quiz: {e}")
        traceback.print_exc()
        return []


def generate_section_quiz(section_title: str, section_text: str, n: int = 2) -> list[Question]:
    """Generate targeted review questions for a single markdown section."""
    if not HAS_OPENAI or not OPENAI_API_KEY:
        return []

    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = f"""Generate {n} review questions based ONLY on this section of a lesson.

SECTION: {section_title}

CONTENT:
{section_text[:2000]}

Generate exactly {n} questions that test understanding of concepts in this specific section.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": PAGE_QUIZ_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=900
        )
        return parse_quiz_response(response.choices[0].message.content)
    except Exception as e:
        print(f"[!] Error generating section quiz: {e}")
        return []


FLASHCARD_PROMPT = """You are a study assistant creating concise flashcards for key technical terms.

For each term provided, write a clear, memorable definition in 1-3 sentences. Focus on:
- What it is
- Why it matters or when to use it
- One concrete distinguishing detail

Format:
TERM: [term]
DEFINITION: [definition]

---
"""


def generate_flashcards(title: str, tags: list[str], summary: str) -> list[dict]:
    """Generate {term, definition} flashcards for key terms from the lesson."""
    if not HAS_OPENAI or not OPENAI_API_KEY:
        return []

    client = OpenAI(api_key=OPENAI_API_KEY)

    terms = ', '.join(tags)
    prompt = f"""Create flashcards for these key terms from the lesson "{title}":

TERMS: {terms}

LESSON CONTEXT: {summary}

Generate one flashcard per term. Keep definitions concise and memorable.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": FLASHCARD_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=1200
        )
        return parse_flashcard_response(response.choices[0].message.content)
    except Exception as e:
        print(f"[!] Error generating flashcards: {e}")
        return []


def parse_flashcard_response(text: str) -> list[dict]:
    """Parse flashcard response into list of {term, definition} dicts."""
    cards = []
    blocks = re.split(r'\n---+\n?', text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        term_match = re.search(r'TERM:\s*(.+)', block)
        def_match = re.search(r'DEFINITION:\s*(.+?)(?=\nTERM:|\Z)', block, re.DOTALL)
        if term_match and def_match:
            cards.append({
                'term': term_match.group(1).strip(),
                'definition': def_match.group(1).strip()
            })
    return cards


def generate_mixed_quiz(topics: list[dict], num_questions: int = 10) -> list[Question]:
    """Generate a mixed quiz from multiple topics."""
    if not HAS_OPENAI:
        print("\n  [!] OpenAI library not installed. Run: pip install openai")
        return []

    if not OPENAI_API_KEY:
        print("\n  [!] OPENAI_API_KEY not set. Export it in your environment.")
        return []

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Gather content from frontmatter
    all_tags = []
    topic_summaries = []

    for topic in topics[:5]:  # Limit to 5 topics for speed
        all_tags.extend(topic.get('tags', []))

        title = topic.get('title', '')
        summary = topic.get('summary', '')
        sections = topic.get('sections', [])

        if summary:
            topic_summaries.append(f"**{title}**: {summary}")
        elif sections:
            topic_summaries.append(f"**{title}**: {'; '.join(sections[:3])}")

    # Deduplicate tags
    all_tags = list(dict.fromkeys(all_tags))

    prompt = f"""Generate {num_questions} Databricks GenAI exam questions.

TOPICS:
{chr(10).join(topic_summaries[:5])}

KEY CONCEPTS: {', '.join(all_tags[:15])}

Generate {num_questions} scenario-based questions. Be concise.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000  # Reduced for speed
        )

        result = parse_quiz_response(response.choices[0].message.content)
        if not result:
            print(f"[!] Parsing failed. Raw response:\n{response.choices[0].message.content[:500]}")
        return result

    except Exception as e:
        import traceback
        print(f"\n  [!] Error generating mixed quiz: {e}")
        traceback.print_exc()
        return []


def parse_quiz_response(text: str) -> list[Question]:
    """Parse OpenAI response into Question objects."""
    questions = []

    # Remove markdown bold/italic formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** -> bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *italic* -> italic

    # Split by OBJECTIVE or Q: markers
    q_blocks = re.split(r'\n(?=OBJECTIVE:|Q:|Question\s*\d)', text)

    for block in q_blocks:
        if not block.strip():
            continue

        try:
            # Extract objective
            obj_match = re.search(r'OBJECTIVE:\s*(.+?)(?=\nQ:|\n\n)', block, re.DOTALL)
            objective = obj_match.group(1).strip() if obj_match else ""

            # Extract question
            q_match = re.search(r'(?:Q:|Question\s*\d*:?)\s*(.+?)(?=\nA\))', block, re.DOTALL)
            if not q_match:
                continue
            question_text = q_match.group(1).strip()

            # Extract options
            options = {}
            for letter in ['A', 'B', 'C', 'D']:
                opt_match = re.search(rf'{letter}\)\s*(.+?)(?=\n[B-D]\)|ANSWER:|$)', block, re.DOTALL)
                if opt_match:
                    options[letter] = opt_match.group(1).strip()

            if len(options) < 4:
                continue

            # Extract answer
            ans_match = re.search(r'ANSWER:\s*([A-D])', block)
            if not ans_match:
                continue
            answer = ans_match.group(1)

            # Extract explanation
            exp_match = re.search(r'EXPLANATION:\s*(.+?)(?=\n---|\nOBJECTIVE:|\nQ:|\Z)', block, re.DOTALL)
            explanation = exp_match.group(1).strip() if exp_match else "No explanation provided."

            questions.append(Question(
                objective=objective,
                question=question_text,
                options=options,
                answer=answer,
                explanation=explanation
            ))

        except Exception:
            continue

    return questions


def run_quiz(questions: list[Question]) -> tuple[int, int]:
    """Run an interactive quiz session. Returns (correct, total)."""
    if not questions:
        print("\n  No questions available.")
        return 0, 0

    correct = 0
    total = len(questions)

    print(f"\n{'=' * 60}")
    print(f"  QUIZ - {total} Questions")
    print(f"{'=' * 60}")

    for i, q in enumerate(questions, 1):
        print(f"\n{'-' * 60}")
        print(f"  Question {i} of {total}")
        print(f"{'-' * 60}")
        print(f"\n{q.question}\n")

        for letter, option in q.options.items():
            print(f"  {letter}) {option}")

        while True:
            user_answer = input("\nYour answer (A/B/C/D or 'q' to quit): ").strip().upper()
            if user_answer == 'Q':
                print(f"\nQuiz ended. Score: {correct}/{i-1}")
                return correct, i - 1
            if user_answer in ['A', 'B', 'C', 'D']:
                break
            print("  Please enter A, B, C, or D")

        if user_answer == q.answer:
            correct += 1
            print(f"\n  CORRECT!")
        else:
            print(f"\n  INCORRECT. The answer was: {q.answer}")

        print(f"\n  Explanation: {q.explanation}")
        print(f"\n  Score so far: {correct}/{i} ({100*correct//i}%)")

        if i < total:
            input("\n  Press Enter to continue...")

    print(f"\n{'=' * 60}")
    print(f"  FINAL SCORE: {correct}/{total} ({100*correct//total}%)")
    print(f"{'=' * 60}")

    return correct, total
