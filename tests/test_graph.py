"""End-to-end topology tests with a scripted LLM (no network, no API key)."""

from typing import Any

from langchain_core.messages import AIMessage

from src.config import MAX_STEPS
from src.graph import build_graph, initial_state
from src.supervisor import SupervisorDecision
from tests.conftest import ScriptedLLM, tool_call

FINDINGS = "- LangGraph kb-01 'excellent control' rating 5"


def decision(next_: str, instructions: str = "") -> SupervisorDecision:
    return SupervisorDecision(reasoning="because", next=next_, instructions=instructions)  # type: ignore[arg-type]


def researcher_turn() -> list[AIMessage]:
    return [tool_call("search_knowledge_base", {"query": "LangGraph"}, "r1"), AIMessage(content=FINDINGS)]


def analyst_turn() -> list[AIMessage]:
    return [
        tool_call("analyze_sentiment", {"texts": ["excellent control"]}, "a1"),
        AIMessage(content="LangGraph average sentiment 1.0"),
    ]


def run(llm: ScriptedLLM) -> dict[str, Any]:
    graph = build_graph(llm)
    return graph.invoke(initial_state("compare frameworks"), config={"recursion_limit": 30})


def visited_nodes(llm: ScriptedLLM) -> list[str]:
    graph = build_graph(llm)
    order: list[str] = []
    for event in graph.stream(initial_state("compare frameworks"), config={"recursion_limit": 30}):
        order.extend(event.keys())
    return order


def test_happy_path_research_then_analysis_then_finish() -> None:
    def make() -> ScriptedLLM:
        return ScriptedLLM(
            messages=iter([*researcher_turn(), *analyst_turn(), AIMessage(content="FINAL")]),
            decisions=[decision("researcher", "find"), decision("analyst", "analyze"), decision("FINISH")],
        )

    assert visited_nodes(make()) == [
        "supervisor", "researcher", "supervisor", "analyst", "supervisor", "synthesizer",
    ]
    state = run(make())
    assert state["task_completed"] is True and state["final_answer"] == "FINAL"
    assert [c["agent"] for c in state["contributions"]] == ["researcher", "analyst"]
    assert state["contributions"][0]["output"] == FINDINGS
    assert state["step_count"] == 3


def test_stubborn_supervisor_cannot_loop_forever() -> None:
    llm = ScriptedLLM(
        messages=iter([*researcher_turn(), *researcher_turn(), *analyst_turn(), AIMessage(content="FINAL")]),
        decisions=[decision("researcher", "again")] * 20,
    )
    state = run(llm)
    assert state["task_completed"] is True
    assert state["step_count"] <= MAX_STEPS
    assert state["visits"]["researcher"] == 2


def test_early_finish_is_rejected_and_work_continues() -> None:
    llm = ScriptedLLM(
        messages=iter([*researcher_turn(), *analyst_turn(), AIMessage(content="FINAL")]),
        decisions=[decision("researcher", "find"), decision("FINISH"), decision("FINISH")],
    )
    state = run(llm)
    assert [c["agent"] for c in state["contributions"]] == ["researcher", "analyst"]
    assert state["task_completed"] is True
