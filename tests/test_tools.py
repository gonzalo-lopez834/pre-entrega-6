import json

from src.tools.analysis_tools import (
    analyze_sentiment,
    calculate,
    compute_statistics,
    safe_eval,
    score_sentiment,
)
from src.tools.research_tools import load_knowledge_base, rank_documents, search_knowledge_base


def test_knowledge_base_loads_three_entities() -> None:
    entities = {doc["entity"] for doc in load_knowledge_base()}
    assert entities == {"LangGraph", "CrewAI", "AutoGen"}


def test_search_returns_only_matching_entity_first() -> None:
    results = json.loads(search_knowledge_base.invoke({"query": "LangGraph opinions", "top_k": 3}))
    assert len(results) == 3
    assert all(doc["entity"] == "LangGraph" for doc in results)


def test_default_search_covers_every_document_of_an_entity() -> None:
    results = json.loads(search_knowledge_base.invoke({"query": "LangGraph opinions"}))
    langgraph_ids = {d["id"] for d in load_knowledge_base() if d["entity"] == "LangGraph"}
    assert langgraph_ids <= {d["id"] for d in results}
    assert len(langgraph_ids) == 6


def test_search_is_accent_insensitive() -> None:
    docs = rank_documents("dificil", load_knowledge_base(), 5)
    assert docs and all("dificil" in d["text"].lower() or "difícil" in d["text"].lower() for d in docs)


def test_search_without_match_returns_empty_list() -> None:
    assert json.loads(search_knowledge_base.invoke({"query": "zzzz qqqq"})) == []


def test_sentiment_polarity_and_negation() -> None:
    assert score_sentiment("excellent and reliable") > 0
    assert score_sentiment("terrible and confusing") < 0
    assert score_sentiment("not good") < 0
    assert score_sentiment("nothing to say") == 0


def test_analyze_sentiment_tool_aggregates() -> None:
    payload = json.loads(analyze_sentiment.invoke({"texts": ["great and easy", "awful and slow", "ok"]}))
    assert payload["count"] == 3
    assert payload["distribution"] == {"positive": 1, "neutral": 1, "negative": 1}
    assert payload["average_score"] == 0.0


def test_compute_statistics() -> None:
    payload = json.loads(compute_statistics.invoke({"values": [5, 4, 3]}))
    assert payload["mean"] == 4.0 and payload["median"] == 4 and payload["max"] == 5
    assert "error" in json.loads(compute_statistics.invoke({"values": []}))


def test_calculate_is_safe() -> None:
    assert safe_eval("(4+5+3)/3") == 4
    assert json.loads(calculate.invoke({"expression": "2**3"}))["result"] == 8
    for bad in ("__import__('os').system('echo hi')", "1/0", "2**9999", "abs(-1)"):
        assert "error" in json.loads(calculate.invoke({"expression": bad}))
