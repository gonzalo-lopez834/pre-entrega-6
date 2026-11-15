"""Deterministic analysis tools: sentiment, descriptive statistics and safe arithmetic."""

import ast
import json
import operator
import re
import statistics
import unicodedata
from typing import Any, Callable

from langchain_core.tools import BaseTool, tool

_POSITIVE = {
    "good", "great", "excellent", "love", "easy", "clear", "powerful", "flexible", "reliable",
    "fast", "intuitive", "helpful", "recommend", "stable", "robust", "best", "perfect", "active",
    "bueno", "buen", "excelente", "genial", "facil", "claro", "potente", "confiable", "rapido",
    "intuitivo", "util", "utiles", "recomiendo", "estable", "robusto", "mejor", "perfecto",
}
_NEGATIVE = {
    "bad", "poor", "terrible", "hate", "hard", "difficult", "confusing", "slow", "buggy",
    "unstable", "broken", "complex", "fragile", "awful", "worst", "lacking", "expensive",
    "loop", "unpredictable", "verbose",
    "malo", "pesimo", "dificil", "confuso", "lento", "inestable", "roto", "complejo", "fragil",
    "horrible", "peor", "limitado", "caro", "compleja", "problema", "problemas",
}
_NEGATIONS = {"not", "no", "never", "nunca", "sin", "ni"}
_TOKEN_RE = re.compile(r"[a-z]+")
_NEUTRAL_BAND = 0.15


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def score_sentiment(text: str) -> float:
    """Return a lexicon sentiment score in [-1, 1] for ``text`` (0 if no cue words).

    A negation word immediately before a cue word flips its polarity.
    """
    words = _TOKEN_RE.findall(_normalize(text))
    positives = negatives = 0
    for index, word in enumerate(words):
        polarity = 1 if word in _POSITIVE else -1 if word in _NEGATIVE else 0
        if polarity == 0:
            continue
        if index > 0 and words[index - 1] in _NEGATIONS:
            polarity = -polarity
        if polarity > 0:
            positives += 1
        else:
            negatives += 1
    total = positives + negatives
    return 0.0 if total == 0 else (positives - negatives) / total


def label_for(score: float) -> str:
    """Map a sentiment score to ``positive`` / ``neutral`` / ``negative``."""
    if score > _NEUTRAL_BAND:
        return "positive"
    if score < -_NEUTRAL_BAND:
        return "negative"
    return "neutral"


@tool
def analyze_sentiment(texts: list[str]) -> str:
    """Compute lexicon-based sentiment (Spanish and English) for a list of texts.

    Returns JSON with a score in [-1, 1] and a label per text, the average score and
    the label distribution. Call it once per entity, passing only that entity's texts.
    """
    results: list[dict[str, Any]] = []
    for text in texts:
        score = round(score_sentiment(text), 3)
        results.append({"text": text[:80], "score": score, "label": label_for(score)})
    scores = [item["score"] for item in results]
    distribution = {
        name: sum(1 for item in results if item["label"] == name)
        for name in ("positive", "neutral", "negative")
    }
    payload = {
        "count": len(results),
        "average_score": round(statistics.fmean(scores), 3) if scores else None,
        "distribution": distribution,
        "results": results,
    }
    return json.dumps(payload, ensure_ascii=False)


@tool
def compute_statistics(values: list[float]) -> str:
    """Compute count, mean, median, min, max and population std-dev of numbers.

    Use it for ratings or any numeric series. Returns JSON.
    """
    if not values:
        return json.dumps({"error": "empty list"})
    payload = {
        "count": len(values),
        "mean": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": min(values),
        "max": max(values),
        "stdev": round(statistics.pstdev(values), 3),
    }
    return json.dumps(payload)


_BINARY_OPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS: dict[type, Callable[[float], float]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _BINARY_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("unsupported expression")


def safe_eval(expression: str) -> float:
    """Evaluate an arithmetic expression without ``eval`` (numbers and + - * / ** % only)."""
    return _eval_node(ast.parse(expression.strip(), mode="eval").body)


@tool
def calculate(expression: str) -> str:
    """Evaluate an arithmetic expression such as "(4+5+3)/3". Supports + - * / ** % and parentheses."""
    try:
        return json.dumps({"expression": expression, "result": round(safe_eval(expression), 6)})
    except (ValueError, SyntaxError, ZeroDivisionError) as exc:
        return json.dumps({"expression": expression, "error": str(exc) or "invalid expression"})


def get_analysis_tools() -> list[BaseTool]:
    """Return the analyst's toolset."""
    return [analyze_sentiment, compute_statistics, calculate]
