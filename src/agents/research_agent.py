"""Research specialist: retrieves facts from external sources."""

from typing import Any, Callable

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

from src.agents.common import clip, make_specialist_node
from src.state import OrchestratorState, latest_contribution
from src.tools.research_tools import get_research_tools

RESEARCH_PROMPT = """You are the Research Specialist of a multi-agent team.

Your only job is to FIND information with your tools. You never analyze, score or compute
averages: another specialist does that.

Rules:
- Always call your search tools before answering. Never answer from memory.
- Run one search per entity or sub-topic (e.g. one query per framework) to get balanced coverage.
- Report findings as a bullet list. Each bullet MUST include: entity, source id (e.g. kb-03),
  the verbatim quote, and any numeric data (e.g. rating).
- Copy every quote exactly as returned by the tool, character by character: never fix,
  merge or rephrase words. Include ALL documents returned for each entity, none omitted.
- Report only what the tools returned. If a search finds nothing, say so explicitly.
- Answer in the same language as the task."""


def build_research_agent(llm: BaseChatModel) -> Any:
    """Create the ReAct research agent with its bounded toolset."""
    return create_agent(llm, tools=get_research_tools(), system_prompt=RESEARCH_PROMPT, name="researcher")


def _research_context(state: OrchestratorState) -> str:
    """On a refinement pass the researcher sees only its own previous output."""
    previous = latest_contribution(state, "researcher")
    return f"Your previous findings (improve them, do not repeat them):\n{clip(previous['output'])}" if previous else ""


def build_research_node(llm: BaseChatModel) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Return the ``researcher`` graph node."""
    return make_specialist_node("researcher", build_research_agent(llm), _research_context)
