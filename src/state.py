"""Shared, structured state of the orchestrator graph."""

import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph import MessagesState

SpecialistName = Literal["researcher", "analyst"]
NextNode = Literal["researcher", "analyst", "synthesizer"]

SPECIALISTS: tuple[SpecialistName, ...] = ("researcher", "analyst")


class Contribution(TypedDict):
    """One specialist output, tagged with who produced it and why."""

    agent: SpecialistName
    step: int  # supervisor decision number that triggered this contribution
    instruction: str  # what the supervisor asked for
    output: str  # what the specialist returned


def merge_visits(left: dict[str, int] | None, right: dict[str, int] | None) -> dict[str, int]:
    """Reducer: merge per-agent visit counters (right wins on conflicts)."""
    return {**(left or {}), **(right or {})}


class OrchestratorState(MessagesState):
    """State shared by the supervisor, the specialists and the synthesizer.

    ``messages`` (inherited) is the public conversation trace. Specialists do NOT
    read it: they receive only their instruction plus the contributions they need,
    which avoids context contamination.
    """

    task: str  # original user request
    next_agent: NextNode  # routing decision written by the supervisor
    instructions: str  # self-contained instruction for the chosen specialist
    supervisor_reasoning: str  # why the supervisor chose ``next_agent``
    contributions: Annotated[list[Contribution], operator.add]  # who said what
    step_count: int  # supervisor decisions taken so far (stop condition)
    visits: Annotated[dict[str, int], merge_visits]  # activations per specialist
    task_completed: bool  # set by the synthesizer
    final_answer: str  # final synthesized answer


def latest_contribution(state: OrchestratorState, agent: SpecialistName) -> Contribution | None:
    """Return the most recent contribution of ``agent`` or ``None``."""
    for contribution in reversed(state.get("contributions", [])):
        if contribution["agent"] == agent:
            return contribution
    return None
