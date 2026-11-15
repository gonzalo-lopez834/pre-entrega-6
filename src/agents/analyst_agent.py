"""Analyst specialist: processes the researcher's findings with deterministic tools."""

from typing import Any, Callable

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

from src.agents.common import clip, make_specialist_node
from src.state import OrchestratorState, latest_contribution
from src.tools.analysis_tools import get_analysis_tools

ANALYST_PROMPT = """You are the Analysis Specialist of a multi-agent team.

You receive findings gathered by the Research Specialist and must analyze them.

Rules:
- Use ONLY data present in the provided findings. Never invent quotes, ratings or sources.
- Never compute anything mentally: use analyze_sentiment for text, compute_statistics for
  number series and calculate for arithmetic.
- Call the tools once per entity, passing only that entity's texts or numbers.
- Report per entity: tool-computed sentiment (average score, distribution) and numeric
  statistics, then a short comparison. Cite source ids (e.g. kb-03) where relevant.
- State any limitation (small sample, missing data) honestly.
- Answer in the same language as the task."""


def build_analyst_agent(llm: BaseChatModel) -> Any:
    """Create the ReAct analyst agent with its bounded toolset."""
    return create_agent(llm, tools=get_analysis_tools(), system_prompt=ANALYST_PROMPT, name="analyst")


def _analyst_context(state: OrchestratorState) -> str:
    """The analyst sees the researcher's latest findings (and its own on refinement)."""
    sections: list[str] = []
    research = latest_contribution(state, "researcher")
    if research:
        sections.append(f"Findings from the Research Specialist:\n{clip(research['output'])}")
    previous = latest_contribution(state, "analyst")
    if previous:
        sections.append(f"Your previous analysis (improve it, do not repeat it):\n{clip(previous['output'])}")
    return "\n\n".join(sections)


def build_analyst_node(llm: BaseChatModel) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Return the ``analyst`` graph node."""
    return make_specialist_node("analyst", build_analyst_agent(llm), _analyst_context)
