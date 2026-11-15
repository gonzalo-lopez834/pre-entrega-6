"""Supervisor (router + quality gate) and final synthesizer nodes."""

from dataclasses import dataclass
from typing import Any, Callable, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents.common import clip, message_text
from src.config import MAX_STEPS, MAX_VISITS_PER_AGENT
from src.state import SPECIALISTS, NextNode, OrchestratorState

SUPERVISOR_PROMPT = f"""You are the Supervisor of a multi-agent research-and-analysis team.

Specialists:
- researcher: retrieves facts (quotes, ratings, sources) with search tools. Does NOT analyze.
- analyst: processes the researcher's findings (sentiment, statistics, calculations). Cannot search.

Given the current state, decide who must act next, or whether it is time to FINISH.

QUALITY RUBRIC - choose FINISH only if ALL of these hold:
1. COVERAGE: the research covers every entity/sub-topic named in the task, with source ids.
2. EVIDENCE: the research contains verbatim quotes or numeric data, not generic statements.
3. QUANTIFICATION: the analysis contains tool-computed numbers (not guesses) for every entity.
4. GROUNDING: the analysis uses only data present in the research (no invented figures).
5. SUFFICIENCY: the contributions together answer the task. Do not ask for perfection.

Routing rules:
- Nothing done yet -> researcher. Research done but not analyzed -> analyst.
- If a rubric criterion fails, send the responsible specialist back ONCE and state exactly
  which criterion failed and what to fix in `instructions`. Prefer FINISH when in doubt.
- `instructions` must be self-contained: the specialist does not see this conversation.
  Leave it empty when you choose FINISH.
- A hard budget of {MAX_STEPS} decisions applies; do not waste steps."""


class SupervisorDecision(BaseModel):
    """Structured routing decision produced by the supervisor LLM."""

    reasoning: str = Field(description="Brief rubric-based justification of the decision.")
    next: Literal["researcher", "analyst", "FINISH"] = Field(
        description="Specialist that must act next, or FINISH when the rubric is satisfied."
    )
    instructions: str = Field(
        default="",
        description="Self-contained instruction for the chosen specialist. Empty on FINISH.",
    )


@dataclass(frozen=True)
class Routing:
    """Final routing after the deterministic guardrails have been applied."""

    next_agent: NextNode
    instructions: str
    note: str = ""


def apply_guardrails(
    decision: SupervisorDecision,
    *,
    step_count: int,
    visits: dict[str, int],
    contributed: set[str],
) -> Routing:
    """Enforce the stop conditions the LLM cannot be trusted to respect.

    - Step budget: once ``MAX_STEPS`` decisions were taken, go straight to synthesis.
    - Both domains required: FINISH is rejected until researcher AND analyst contributed.
    - Dependency: the analyst never runs before the researcher produced something.
    - Refinement cap: a specialist is activated at most ``MAX_VISITS_PER_AGENT`` times.
    """
    if step_count >= MAX_STEPS:
        return Routing("synthesizer", "", f"step budget of {MAX_STEPS} exhausted")

    requested: NextNode = "synthesizer" if decision.next == "FINISH" else decision.next
    instructions = decision.instructions
    note = ""

    def reroute(target: NextNode, why: str) -> None:
        nonlocal requested, instructions, note
        requested, instructions, note = target, "", why

    if requested == "synthesizer":
        missing = [agent for agent in SPECIALISTS if agent not in contributed]
        if missing:
            reroute(missing[0], f"FINISH rejected: no contribution from {missing[0]} yet")
    elif requested == "analyst" and "researcher" not in contributed:
        reroute("researcher", "analyst blocked: nothing to analyze yet")

    if requested != "synthesizer" and visits.get(requested, 0) >= MAX_VISITS_PER_AGENT:
        pending = [a for a in SPECIALISTS if a not in contributed and visits.get(a, 0) < MAX_VISITS_PER_AGENT]
        if pending:
            reroute(pending[0], f"{requested} reached its refinement limit")
        else:
            reroute("synthesizer", f"{requested} reached its refinement limit")

    return Routing(requested, instructions, note)


def _digest(state: OrchestratorState) -> str:
    """Summarize what each agent has contributed so far for the supervisor prompt."""
    contributions = state.get("contributions", [])
    if not contributions:
        return "(no contributions yet)"
    return "\n\n".join(
        f"[decision {c['step']}] {c['agent'].upper()} (asked: {c['instruction'][:200]})\n{clip(c['output'], 3500)}"
        for c in contributions
    )


def make_supervisor_node(llm: BaseChatModel) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Build the supervisor node: structured LLM decision + deterministic guardrails."""
    decider = llm.with_structured_output(SupervisorDecision)

    def supervisor(state: OrchestratorState) -> dict[str, Any]:
        step_count = state.get("step_count", 0)
        visits = state.get("visits", {})
        contributed = {c["agent"] for c in state.get("contributions", [])}
        user_prompt = (
            f"TASK:\n{state['task']}\n\n"
            f"Decisions taken so far: {step_count}/{MAX_STEPS}. Activations: {visits or 'none'}.\n\n"
            f"CONTRIBUTIONS SO FAR:\n{_digest(state)}"
        )
        decision: SupervisorDecision = decider.invoke(
            [SystemMessage(content=SUPERVISOR_PROMPT), HumanMessage(content=user_prompt)]
        )
        routing = apply_guardrails(decision, step_count=step_count, visits=visits, contributed=contributed)
        reasoning = decision.reasoning + (f" [guardrail: {routing.note}]" if routing.note else "")
        update: dict[str, Any] = {
            "next_agent": routing.next_agent,
            "instructions": routing.instructions,
            "supervisor_reasoning": reasoning,
            "step_count": step_count + 1,
        }
        if routing.next_agent != "synthesizer":
            update["visits"] = {routing.next_agent: visits.get(routing.next_agent, 0) + 1}
        return update

    return supervisor


def route_from_supervisor(state: OrchestratorState) -> NextNode:
    """Conditional-edge router: maps the supervisor decision to a node name."""
    return state["next_agent"]


SYNTHESIZER_PROMPT = """You are the final Synthesizer of a multi-agent team.
Write the final answer to the user's task using ONLY the contributions provided.
- Be concise and structured; cite source ids (e.g. kb-03) for key claims.
- Attribute facts to the research and numbers to the analysis; do not add new data.
- Mention any limitation the contributions report.
- Answer in the same language as the task."""


def make_synthesizer_node(llm: BaseChatModel) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Build the synthesis node that closes the run and marks the task completed."""

    def synthesizer(state: OrchestratorState) -> dict[str, Any]:
        user_prompt = f"TASK:\n{state['task']}\n\nCONTRIBUTIONS:\n{_digest(state)}"
        reply = llm.invoke([SystemMessage(content=SYNTHESIZER_PROMPT), HumanMessage(content=user_prompt)])
        answer = message_text(reply).strip()
        return {
            "final_answer": answer,
            "task_completed": True,
            "messages": [AIMessage(content=answer, name="synthesizer")],
        }

    return synthesizer
