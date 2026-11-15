"""Central configuration: environment variables, paths and orchestration limits."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = ROOT_DIR / "data"
LOGS_DIR: Path = ROOT_DIR / "logs"
DOCS_DIR: Path = ROOT_DIR / "docs"

load_dotenv(ROOT_DIR / ".env")

DEFAULT_MODEL_NAME: str = "gemini-3.5-flash-lite"
MODEL_NAME: str = os.getenv("MODEL_NAME") or DEFAULT_MODEL_NAME

# Stop conditions that prevent the "infinite supervisor" loop.
MAX_STEPS: int = 6  # maximum number of supervisor decisions per run
MAX_VISITS_PER_AGENT: int = 2  # first pass + at most one refinement
RECURSION_LIMIT: int = 30  # LangGraph hard ceiling (safety net)


def get_llm() -> ChatGoogleGenerativeAI:
    """Build the Gemini chat model used by every node.

    ``temperature`` is intentionally not passed: the configured model ignores it.

    Raises:
        RuntimeError: if ``GOOGLE_API_KEY`` is not set.
    """
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return ChatGoogleGenerativeAI(model=MODEL_NAME)
