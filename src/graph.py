"""Graph assembly: supervisor -> specialists -> supervisor ... -> synthesizer -> END."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents import build_analyst_node, build_research_node
from src.config import DOCS_DIR, get_llm
from src.state import OrchestratorState
from src.supervisor import (
    make_supervisor_node,
    make_synthesizer_node,
    route_from_supervisor,
)


def build_graph(llm: BaseChatModel | None = None) -> CompiledStateGraph:
    """Compile the orchestrator graph.

    Args:
        llm: chat model shared by all nodes. Defaults to the configured Gemini model.
    """
    llm = llm or get_llm()
    builder = StateGraph(OrchestratorState)
    builder.add_node("supervisor", make_supervisor_node(llm))
    builder.add_node("researcher", build_research_node(llm))
    builder.add_node("analyst", build_analyst_node(llm))
    builder.add_node("synthesizer", make_synthesizer_node(llm))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"researcher": "researcher", "analyst": "analyst", "synthesizer": "synthesizer"},
    )
    builder.add_edge("researcher", "supervisor")
    builder.add_edge("analyst", "supervisor")
    builder.add_edge("synthesizer", END)
    return builder.compile()


def initial_state(task: str) -> dict[str, Any]:
    """Build the initial state for a user task."""
    return {
        "task": task,
        "messages": [HumanMessage(content=task)],
        "contributions": [],
        "visits": {},
        "step_count": 0,
        "task_completed": False,
        "final_answer": "",
    }


def export_diagram(graph: CompiledStateGraph) -> None:
    """Write the Mermaid source (always) and a PNG (best effort) under ``docs/``.

    The PNG is rendered by the mermaid.ink web service, so it needs internet access.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    mermaid = graph.get_graph().draw_mermaid()
    (DOCS_DIR / "graph.mmd").write_text(mermaid, encoding="utf-8")
    print(f"Mermaid source written to {DOCS_DIR / 'graph.mmd'}")
    try:
        (DOCS_DIR / "graph.png").write_bytes(graph.get_graph().draw_mermaid_png())
        print(f"PNG written to {DOCS_DIR / 'graph.png'}")
    except Exception as exc:  # network/service failure must not break the export
        print(f"PNG not generated ({type(exc).__name__}); the .mmd file is enough for the README.")


if __name__ == "__main__":
    export_diagram(build_graph())
