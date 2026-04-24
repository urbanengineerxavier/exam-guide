#!/usr/bin/env python3
"""Streamlit web UI for Databricks GenAI Exam Study Tool."""

import base64
import hashlib
import json
import re
import random
import streamlit as st
import yaml
from pathlib import Path
from config import RESOURCES_PATH, OPENAI_API_KEY, OPENAI_MODEL, TAG_TO_EXAM, EXAM_SECTIONS, CACHE_PATH, EXAM_GUIDE_PATH
from quiz import generate_mixed_quiz, generate_page_quiz, generate_section_recap, Question

# Page config
st.set_page_config(
    page_title="Databricks GenAI Study",
    page_icon="📚",
    layout="centered"
)

# Custom CSS
st.markdown("""
<style>
    .exam-badge {
        background: #1f77b4;
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-size: 0.85rem;
        margin-right: 0.5rem;
    }
    .type-badge {
        background: #2ca02c;
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-size: 0.85rem;
    }
    .nav-info {
        text-align: center;
        color: #888;
        padding: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


_exam_guide_cache: dict = {}


def _cache_file(prefix: str, *keys: str) -> Path:
    h = hashlib.md5("__".join(keys).encode()).hexdigest()
    return CACHE_PATH / f"{prefix}_{h}.json"


def get_exam_objectives(tags: list) -> str:
    """Extract relevant exam objectives from the exam guide for the given tags."""
    if not _exam_guide_cache:
        if EXAM_GUIDE_PATH.exists():
            _exam_guide_cache['text'] = EXAM_GUIDE_PATH.read_text(encoding='utf-8')
        else:
            return ""

    guide_text = _exam_guide_cache.get('text', '')
    sections = {tag: TAG_TO_EXAM.get(tag) for tag in tags if tag in TAG_TO_EXAM}
    target_sections = set(s for s in sections.values() if s)

    if not target_sections:
        return ""

    objectives = []
    for section_name in target_sections:
        # Find the section block in the exam guide
        pattern = rf'(?:Section \d+[:\s]+)?{re.escape(section_name)}.*?(?=\n##|\nSection \d|\Z)'
        match = re.search(pattern, guide_text, re.DOTALL | re.IGNORECASE)
        if match:
            objectives.append(match.group(0).strip())

    return "\n\n".join(objectives)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown."""
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1])
                return meta or {}, parts[2].strip()
            except yaml.YAMLError:
                pass
    return {}, content


def embed_images(text: str, file_path: Path) -> str:
    """Replace relative <img src="..."> with base64 data URIs so Streamlit can display them."""
    def replace_img(match):
        src = match.group(1)
        if src.startswith('http'):
            return match.group(0)  # Leave external URLs alone
        img_path = (file_path.parent / src).resolve()
        if img_path.exists():
            ext = img_path.suffix.lstrip('.').lower()
            mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
            data = base64.b64encode(img_path.read_bytes()).decode()
            # Preserve any extra attributes (alt, width, etc.) from the original tag
            extra = match.group(2) or ''
            return f'<img src="data:{mime};base64,{data}"{extra}>'
        return ''  # Image not found — remove the broken tag

    # Match <img src="..." ...> capturing src and remaining attributes separately
    text = re.sub(
        r'<img\s+src=["\']([^"\']+)["\']([^>]*)/?>',
        replace_img,
        text,
        flags=re.IGNORECASE
    )
    return text


def clean_html(text: str, file_path: Path = None) -> str:
    """Remove unwanted HTML tags and clean up content. Preserves images."""
    # Remove div tags with content
    text = re.sub(r'<div[^>]*>.*?</div>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove remaining non-img HTML tags
    text = re.sub(r'<(?!img\b)[^>]+>', '', text, flags=re.IGNORECASE)
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def split_by_sections(body: str) -> list[tuple[str | None, str]]:
    """Split markdown body into (heading, content) pairs on ## headings.
    Content before the first ## heading is returned as (None, content).
    Only actual ## sections get a heading — never add checkpoints to None entries.
    """
    parts = re.split(r'\n(## [^\n]+)', body)
    result = []
    # parts[0] is everything before the first ## heading
    if parts[0].strip():
        result.append((None, parts[0].strip()))
    # remaining parts alternate: heading line, content
    for i in range(1, len(parts), 2):
        heading = parts[i].lstrip('#').strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ''
        result.append((heading, content))
    return result


def should_add_recap(heading: str) -> bool:
    """Return True for substantive sections that warrant a recap."""
    skip = {'introduction', 'lesson objectives', 'summary', 'objectives'}
    h = heading.lower()
    if any(h == s or h.startswith(s) for s in skip):
        return False
    return True


def render_section_recap(file_key: str, heading: str, section_text: str):
    """Render a coloured recap summary after a section."""
    state_key = f"{file_key}__recap__{heading}"

    if 'section_recaps' not in st.session_state:
        st.session_state.section_recaps = {}

    recap = st.session_state.section_recaps.get(state_key)

    if recap is None:
        # Check disk cache first
        cf = _cache_file("recap", file_key, heading)
        if cf.exists():
            recap = json.loads(cf.read_text())["recap"]
            st.session_state.section_recaps[state_key] = recap
        elif OPENAI_API_KEY:
            with st.spinner("Generating recap..."):
                recap = generate_section_recap(heading, section_text)
                cf.write_text(json.dumps({"recap": recap}))
                st.session_state.section_recaps[state_key] = recap
                st.rerun()

    if recap:
        st.info(f"**📌 Recap — {heading}**\n\n{recap}")


def render_page_quiz(file_key: str, meta: dict, content: str):
    """Render a 5-10 question quiz at the bottom of a lesson page."""
    st.subheader("📝 Page Quiz")

    if 'page_quiz' not in st.session_state:
        st.session_state.page_quiz = {}

    state = st.session_state.page_quiz.get(file_key, {})
    questions = state.get('questions')

    if questions is None:
        # Check disk cache first
        cf = _cache_file("quiz", file_key)
        if cf.exists():
            raw = json.loads(cf.read_text())
            questions = [Question(**q) for q in raw]
            st.session_state.page_quiz[file_key] = {'questions': questions, 'answers': {}, 'submitted': False}
        elif OPENAI_API_KEY:
            with st.spinner("Generating quiz..."):
                num_q = random.randint(5, 10)
                objectives = get_exam_objectives(meta.get('tags', []))
                questions = generate_page_quiz(
                    meta.get('title', ''), content,
                    num_questions=num_q, exam_objectives=objectives
                )
                cf.write_text(json.dumps([q.__dict__ for q in questions]))
                st.session_state.page_quiz[file_key] = {'questions': questions, 'answers': {}, 'submitted': False}
                st.rerun()
        else:
            st.warning("Set OPENAI_API_KEY to enable the page quiz.")
            return

    if not questions:
        st.warning("Could not generate quiz for this page.")
        return

    total = len(questions)
    answers = st.session_state.page_quiz[file_key]['answers']
    submitted = st.session_state.page_quiz[file_key]['submitted']

    if not submitted:
        answered = len(answers)
        st.progress(answered / total, f"Answered: {answered}/{total}")

        for i, q in enumerate(questions):
            st.markdown(f"**Q{i+1}: {q.question}**")
            current_ans = answers.get(i)
            for letter, option in q.options.items():
                btn_type = "primary" if current_ans == letter else "secondary"
                if st.button(f"{letter}) {option}", key=f"pq_{file_key}_{i}_{letter}",
                             type=btn_type, use_container_width=True):
                    st.session_state.page_quiz[file_key]['answers'][i] = letter
                    st.rerun()
            st.markdown("")

        if len(answers) == total:
            if st.button("📊 Submit Quiz", type="primary", use_container_width=True):
                st.session_state.page_quiz[file_key]['submitted'] = True
                st.rerun()
    else:
        correct = 0
        for i, q in enumerate(questions):
            user_ans = answers.get(i, "")
            is_correct = user_ans == q.answer
            if is_correct:
                correct += 1
            icon = "✅" if is_correct else "❌"
            with st.expander(f"{icon} Q{i+1}: {q.question[:60]}...", expanded=not is_correct):
                for letter, option in q.options.items():
                    if letter == q.answer:
                        st.success(f"{letter}) {option} ✓")
                    elif letter == user_ans:
                        st.error(f"{letter}) {option} ✗")
                    else:
                        st.write(f"{letter}) {option}")
                st.info(f"💡 {q.explanation}")

        pct = int(100 * correct / total)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Score", f"{correct}/{total}", f"{pct}%")
        with col2:
            if pct >= 70:
                st.success("🎉 Passing score!")
            else:
                st.warning("📚 Keep studying!")

        if st.button("🔄 New Quiz", key=f"pq_retake_{file_key}"):
            # Clear disk cache so a fresh set of questions is generated
            cf = _cache_file("quiz", file_key)
            if cf.exists():
                cf.unlink()
            del st.session_state.page_quiz[file_key]
            st.rerun()


def get_exam_badge(tags: list) -> str:
    """Get primary exam section from tags."""
    for tag in tags:
        if tag in TAG_TO_EXAM:
            return TAG_TO_EXAM[tag]
    return "General"


@st.cache_data
def get_folder_structure():
    """Get courses and topics from folder structure."""
    courses = {}

    for course_dir in sorted(RESOURCES_PATH.iterdir()):
        if course_dir.is_dir() and not course_dir.name.startswith('.'):
            topics = {}

            for topic_dir in sorted(course_dir.iterdir()):
                if topic_dir.is_dir() and not topic_dir.name.startswith('.'):
                    files = sorted(topic_dir.glob("*.md"))
                    if files:
                        topics[topic_dir.name] = [str(f) for f in files]

            if topics:
                courses[course_dir.name] = topics

    # Also include root-level md files (like exam guide)
    root_files = sorted(RESOURCES_PATH.glob("*.md"))
    if root_files:
        courses["Reference Materials"] = {"Guides": [str(f) for f in root_files]}

    return courses


def show_sidebar():
    """Show navigation sidebar."""
    with st.sidebar:
        st.title("📚 Study Tool")
        st.caption("Databricks GenAI Exam")

        st.divider()

        page = st.radio(
            "Navigate",
            ["🏠 Home", "📖 Study", "📝 Quiz"],
            label_visibility="collapsed"
        )

        st.divider()

        if OPENAI_API_KEY:
            st.success("✓ OpenAI API ready")
        else:
            st.warning("⚠ Set OPENAI_API_KEY")

        return page


def show_home():
    """Show home page."""
    st.title("Databricks Certified GenAI Engineer")
    st.caption("Associate Exam Study Tool")

    courses = get_folder_structure()

    # Count files
    total_files = sum(len(files) for topics in courses.values() for files in topics.values())

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Courses", len(courses))
    with col2:
        st.metric("Lessons", total_files)

    st.divider()
    st.subheader("Course Structure")

    for course_name, topics in courses.items():
        topic_count = len(topics)
        file_count = sum(len(files) for files in topics.values())

        with st.expander(f"**{course_name}** - {topic_count} topics, {file_count} lessons"):
            for topic_name, files in topics.items():
                st.write(f"📁 **{topic_name}** ({len(files)} files)")
                for f in files[:3]:
                    st.caption(f"  └ {Path(f).stem}")
                if len(files) > 3:
                    st.caption(f"  └ ... and {len(files) - 3} more")

    st.divider()
    st.subheader("Exam Sections")
    for section, weight in EXAM_SECTIONS.items():
        st.write(f"• **{section}** ({weight})")


def get_chat_response(messages: list[dict], title: str, content: str) -> str:
    """Get a response from the chatbot grounded in the current lesson."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    system = f"""You are a helpful study assistant for a Databricks Generative AI certification course.

The student is currently studying this lesson: {title}

LESSON CONTENT:
{content[:4000]}

Your role:
- Answer questions about this lesson clearly and helpfully
- Feel free to explain concepts in more depth than the document covers — use analogies and examples
- If asked about something not explicitly in the lesson, use your knowledge to help
- Keep answers focused and concise"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Sorry, I couldn't generate a response: {e}"


def render_chat_panel(file_key: str, meta: dict, content: str):
    """Render the contextual chatbot panel for the current lesson."""
    st.subheader("💬 Ask a Question")

    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = {}

    msgs = st.session_state.chat_messages.get(file_key, [])

    # Display chat history
    for msg in msgs:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask anything about this lesson..."):
        if not OPENAI_API_KEY:
            st.error("Set OPENAI_API_KEY in your .env file to use the chatbot.")
        else:
            msgs.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner(""):
                    reply = get_chat_response(msgs, meta.get('title', ''), content)
                st.markdown(reply)
            msgs.append({"role": "assistant", "content": reply})
            st.session_state.chat_messages[file_key] = msgs

    if msgs:
        if st.button("🗑 Clear chat", key=f"clear_chat_{file_key}"):
            st.session_state.chat_messages[file_key] = []
            st.rerun()


def show_study():
    """Show study mode with folder-based navigation."""
    st.title("📖 Study Mode")

    courses = get_folder_structure()

    if not courses:
        st.error("No content found in resources_v2/")
        return

    # Initialize session state for navigation
    if 'study_file_idx' not in st.session_state:
        st.session_state.study_file_idx = 0

    # Course selector
    course_names = list(courses.keys())
    selected_course = st.selectbox("Course", course_names, key="course_select")

    # Topic selector
    topics = courses[selected_course]
    topic_names = list(topics.keys())
    selected_topic = st.selectbox("Topic", topic_names, key="topic_select")

    # Get files for selected topic
    files = topics[selected_topic]

    # Reset file index when topic changes
    if 'last_topic' not in st.session_state or st.session_state.last_topic != selected_topic:
        st.session_state.study_file_idx = 0
        st.session_state.last_topic = selected_topic

    # Ensure file index is valid
    file_idx = min(st.session_state.study_file_idx, len(files) - 1)

    # File selector
    file_names = [Path(f).stem for f in files]
    selected_file_idx = st.selectbox(
        "Lesson",
        range(len(files)),
        index=file_idx,
        format_func=lambda i: file_names[i],
        key="file_select"
    )

    # Update session state
    st.session_state.study_file_idx = selected_file_idx

    # Load and parse file
    current_file = Path(files[selected_file_idx])
    content = current_file.read_text(encoding='utf-8')
    meta, body = parse_frontmatter(content)

    # Show metadata badges
    col1, col2, col3 = st.columns(3)
    with col1:
        exam_section = get_exam_badge(meta.get('tags', []))
        st.markdown(f"📋 **Exam:** {exam_section}")
    with col2:
        lesson_type = meta.get('type', 'content').title()
        st.markdown(f"📝 **Type:** {lesson_type}")
    with col3:
        st.markdown(f"📄 **File:** {selected_file_idx + 1} of {len(files)}")

    # Show summary if available
    if meta.get('summary'):
        st.info(f"**Summary:** {meta['summary']}")

    st.divider()

    # Render content section by section with checkpoints after each substantive section
    file_key = str(current_file)
    clean_body = clean_html(body)
    sections = split_by_sections(clean_body)

    for heading, content in sections:
        if heading is None:
            # Content before the first ## heading (title, preamble) — no checkpoint
            rendered = embed_images(content, current_file)
            st.markdown(rendered, unsafe_allow_html=True)
        else:
            rendered = embed_images(f"## {heading}\n\n{content}", current_file)
            st.markdown(rendered, unsafe_allow_html=True)
            if should_add_recap(heading):
                render_section_recap(file_key, heading, content)

    # End-of-page quiz
    st.divider()
    render_page_quiz(file_key, meta, clean_body)

    # Contextual chatbot
    st.divider()
    render_chat_panel(file_key, meta, clean_body)

    # Navigation buttons
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if selected_file_idx > 0:
            if st.button("← Previous", use_container_width=True):
                st.session_state.study_file_idx = selected_file_idx - 1
                st.rerun()

    with col2:
        st.markdown(f"<p class='nav-info'>{selected_file_idx + 1} of {len(files)}</p>",
                    unsafe_allow_html=True)

    with col3:
        if selected_file_idx < len(files) - 1:
            if st.button("Next →", use_container_width=True):
                st.session_state.study_file_idx = selected_file_idx + 1
                st.rerun()


def show_quiz():
    """Show quiz mode."""
    st.title("📝 Quiz Mode")

    # Session state
    if 'quiz_questions' not in st.session_state:
        st.session_state.quiz_questions = []
    if 'quiz_current' not in st.session_state:
        st.session_state.quiz_current = 0
    if 'quiz_answers' not in st.session_state:
        st.session_state.quiz_answers = {}
    if 'quiz_submitted' not in st.session_state:
        st.session_state.quiz_submitted = False

    courses = get_folder_structure()

    # Setup phase
    if not st.session_state.quiz_questions:
        st.subheader("Configure Quiz")

        col1, col2 = st.columns(2)
        with col1:
            quiz_scope = st.radio("Quiz Scope", ["Single Topic", "Full Course", "All Content"])
        with col2:
            num_q = st.slider("Questions", 3, 10, 5)

        # Topic selection based on scope
        if quiz_scope == "Single Topic":
            course = st.selectbox("Course", list(courses.keys()))
            topic = st.selectbox("Topic", list(courses[course].keys()))
            files = courses[course][topic]
        elif quiz_scope == "Full Course":
            course = st.selectbox("Course", list(courses.keys()))
            files = []
            for topic_files in courses[course].values():
                files.extend(topic_files)
        else:
            files = []
            for topics in courses.values():
                for topic_files in topics.values():
                    files.extend(topic_files)

        if st.button("🎯 Generate Quiz", type="primary"):
            if not OPENAI_API_KEY:
                st.error("Set OPENAI_API_KEY in .env file")
                return

            with st.spinner("Generating questions..."):
                try:
                    # Load content from selected files
                    topics_data = []
                    sample_files = random.sample(files, min(5, len(files)))

                    for f in sample_files:
                        content = Path(f).read_text(encoding='utf-8')
                        meta, body = parse_frontmatter(content)
                        topics_data.append({
                            'title': meta.get('title', Path(f).stem),
                            'summary': meta.get('summary', ''),
                            'tags': meta.get('tags', []),
                            'sections': meta.get('sections', []),
                            'body': clean_html(body)[:2000]  # Limit for API
                        })

                    questions = generate_mixed_quiz(topics_data, num_q)

                    if questions:
                        st.session_state.quiz_questions = questions
                        st.session_state.quiz_current = 0
                        st.session_state.quiz_answers = {}
                        st.session_state.quiz_submitted = False
                        st.rerun()
                    else:
                        st.error("No questions generated. Check terminal for errors.")
                except Exception as e:
                    st.error(f"Error: {e}")
        return

    # Quiz in progress
    questions = st.session_state.quiz_questions
    total = len(questions)

    if not st.session_state.quiz_submitted:
        # Progress
        answered = len(st.session_state.quiz_answers)
        st.progress(answered / total, f"Answered: {answered}/{total}")

        q_idx = st.session_state.quiz_current
        q = questions[q_idx]

        st.markdown(f"### Question {q_idx + 1} of {total}")

        if q.objective:
            st.caption(f"**Objective:** {q.objective}")

        st.markdown(f"**{q.question}**")

        # Options
        current_ans = st.session_state.quiz_answers.get(q_idx)

        for letter, option in q.options.items():
            selected = current_ans == letter
            btn_type = "primary" if selected else "secondary"
            if st.button(f"{letter}) {option}", key=f"opt_{q_idx}_{letter}",
                        type=btn_type, use_container_width=True):
                st.session_state.quiz_answers[q_idx] = letter
                st.rerun()

        # Navigation
        st.divider()
        col1, col2, col3 = st.columns([1, 2, 1])

        with col1:
            if q_idx > 0:
                if st.button("← Previous"):
                    st.session_state.quiz_current -= 1
                    st.rerun()

        with col2:
            if len(st.session_state.quiz_answers) == total:
                if st.button("📊 Submit Quiz", type="primary", use_container_width=True):
                    st.session_state.quiz_submitted = True
                    st.rerun()

        with col3:
            if q_idx < total - 1:
                if st.button("Next →"):
                    st.session_state.quiz_current += 1
                    st.rerun()

    else:
        # Results
        st.subheader("Results")

        correct = 0
        for i, q in enumerate(questions):
            user_ans = st.session_state.quiz_answers.get(i, "")
            is_correct = user_ans == q.answer
            if is_correct:
                correct += 1

            icon = "✅" if is_correct else "❌"
            with st.expander(f"{icon} Q{i+1}: {q.question[:50]}...", expanded=not is_correct):
                if q.objective:
                    st.caption(f"Objective: {q.objective}")

                for letter, option in q.options.items():
                    if letter == q.answer:
                        st.success(f"{letter}) {option} ✓")
                    elif letter == user_ans:
                        st.error(f"{letter}) {option} ✗")
                    else:
                        st.write(f"{letter}) {option}")

                st.info(f"**Explanation:** {q.explanation}")

        pct = int(100 * correct / total)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Score", f"{correct}/{total}", f"{pct}%")
        with col2:
            if pct >= 70:
                st.success("🎉 Passing score!")
            else:
                st.warning("📚 Keep studying!")

        if st.button("🔄 New Quiz"):
            st.session_state.quiz_questions = []
            st.rerun()


def main():
    page = show_sidebar()

    if page == "🏠 Home":
        show_home()
    elif page == "📖 Study":
        show_study()
    elif page == "📝 Quiz":
        show_quiz()


if __name__ == "__main__":
    main()
