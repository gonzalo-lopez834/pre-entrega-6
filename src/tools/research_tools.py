"""Research tools: a local knowledge-base search and an optional Tavily web search."""

import json
import os
import re
import unicodedata
from functools import lru_cache
from typing import Any

from langchain_core.tools import BaseTool, tool

from src.config import DATA_DIR

KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge_base.json"
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase and strip accents so 'dificil' matches 'difícil'."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokens(text: str) -> set[str]:
    """Return the set of meaningful tokens (length >= 3) of ``text``."""
    return {tok for tok in _TOKEN_RE.findall(_normalize(text)) if len(tok) >= 3}


@lru_cache(maxsize=1)
def load_knowledge_base() -> tuple[dict[str, Any], ...]:
    """Load the sample knowledge base from ``data/knowledge_base.json``."""
    with KNOWLEDGE_BASE_PATH.open(encoding="utf-8") as handle:
        return tuple(json.load(handle))


def rank_documents(query: str, documents: tuple[dict[str, Any], ...], top_k: int) -> list[dict[str, Any]]:
    """Rank documents by token overlap with ``query`` (ties broken by id).

    Documents with no overlap are dropped. Entity names weigh double.
    """
    query_tokens = _tokens(query)
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for doc in documents:
        entity_tokens = _tokens(doc["entity"])
        body_tokens = _tokens(doc["text"]) | entity_tokens
        score = len(query_tokens & body_tokens) + len(query_tokens & entity_tokens)
        if score > 0:
            scored.append((score, doc["id"], doc))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [doc for _, _, doc in scored[:top_k]]


@tool
def search_knowledge_base(query: str, top_k: int = 10) -> str:
    """Search the local knowledge base of community opinions about agent frameworks.

    Use one query per entity (e.g. "LangGraph opinions") to get balanced results.
    Returns up to ``top_k`` (default 10, max 10) documents, so one query covers an entity.
    Returns a JSON list of documents with id, entity, source, rating (1-5) and text.
    """
    results = rank_documents(query, load_knowledge_base(), max(1, min(top_k, 10)))
    if not results:
        return json.dumps([])
    return json.dumps(results, ensure_ascii=False)


def get_research_tools() -> list[BaseTool]:
    """Return the research toolset.

    The local knowledge-base search is always available. Tavily web search is added
    only when ``TAVILY_API_KEY`` is configured.
    """
    tools: list[BaseTool] = [search_knowledge_base]
    if os.getenv("TAVILY_API_KEY"):
        from langchain_tavily import TavilySearch

        tools.append(TavilySearch(max_results=3))
    return tools
