"""Configuration for the Databricks GenAI Exam Study Tool."""

import os
from pathlib import Path

# Paths
BASE_PATH = Path(__file__).parent.parent
RESOURCES_PATH = BASE_PATH / "resources_v2"

# Load .env file if it exists
ENV_FILE = BASE_PATH / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().strip().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
try:
    import streamlit as st
    OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", OPENAI_API_KEY)
except Exception:
    pass
OPENAI_MODEL = "gpt-4o-mini"

# Map tags to exam sections (for badge display)
TAG_TO_EXAM = {
    # Data Preparation (18%)
    'document-parsing': 'Data Preparation',
    'chunking': 'Data Preparation',
    'embeddings': 'Data Preparation',
    'Delta-Lake': 'Data Preparation',
    'vector-search': 'Data Preparation',
    'ai_parse_document': 'Data Preparation',

    # Design Applications (22%)
    'RAG': 'Design Applications',
    'context-engineering': 'Design Applications',
    'prompt-engineering': 'Design Applications',
    'grounding': 'Design Applications',
    'token-budget': 'Design Applications',

    # Application Development (18%)
    'LangChain': 'Application Development',
    'MLflow': 'Application Development',
    'agent-framework': 'Application Development',
    'DSPy': 'Application Development',
    'tracing': 'Application Development',

    # Assembling & Deploying (18%)
    'Unity-Catalog': 'Assembling & Deploying',
    'model-serving': 'Assembling & Deploying',
    'AI-agents': 'Assembling & Deploying',
    'tool-registration': 'Assembling & Deploying',

    # Governance (12%)
    'guardrails': 'Governance',
    'governance': 'Governance',

    # Evaluation & Monitoring (12%)
    'evaluation': 'Evaluation & Monitoring',
    'monitoring': 'Evaluation & Monitoring',
}

# Exam sections for reference
EXAM_SECTIONS = {
    'Design Applications': '22%',
    'Data Preparation': '18%',
    'Application Development': '18%',
    'Assembling & Deploying': '18%',
    'Governance': '12%',
    'Evaluation & Monitoring': '12%',
}
