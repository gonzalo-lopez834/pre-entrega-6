"""Helpers shared by the specialist agents."""

from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from src.state import Contribution, OrchestratorState, SpecialistName

ContextBuilder = Callable[[OrchestratorState], str]
MAX_CONTEXT_CHARS = 6000


def message_text(message: BaseMessage) -> str:
    """Extract plain text from a message (Gemini may return a list of content blocks)."""
    content: Any = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def clip(text: str, limit: int = MAX_CONTEXT_CHARS) -> str:
    """Truncate ``text`` to ``limit`` characters, marking the cut."""
    return text if len(text) <= limit else text[:limit] + "\n[...truncated...]"


def make_specialist_node(
    name: SpecialistName,
    agent: CompiledStateGraph,
    build_context: ContextBuilder,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    """Wrap a ReAct agent as a graph node with an isolated context.

    The agent never sees the shared message history. It receives only:
    the supervisor's instruction (falling back to the original task) plus the
    context produced by ``build_context`` (e.g. the researcher's findings).
    Its result is stored as a tagged ``Contribution`` so provenance is never lost.
    """

    def node(state: OrchestratorState) -> dict[str, Any]:
        instruction = state.get("instructions") or state["task"]
        context = build_context(state)
        prompt = f"TASK FOR YOU:\n{instruction}"
        if context:
            prompt += f"\n\nCONTEXT YOU MAY USE:\n{context}"
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        output = message_text(result["messages"][-1]).strip()
        contribution: Contribution = {
            "agent": name,
            "step": state.get("step_count", 0),
            "instruction": instruction,
            "output": output,
        }
        return {
            "contributions": [contribution],
            "messages": [AIMessage(content=output, name=name)],
        }

    node.__name__ = f"{name}_node"
    return node
