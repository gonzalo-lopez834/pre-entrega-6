"""CLI entry point: ``python -m src.main "your task"``."""

import sys
from datetime import datetime
from typing import Any

from src.config import LOGS_DIR, MODEL_NAME, RECURSION_LIMIT
from src.graph import build_graph, initial_state

DEFAULT_TASK = (
    "Investiga que opina la comunidad sobre LangGraph, CrewAI y AutoGen para orquestar "
    "agentes, y analiza el sentimiento y el puntaje promedio de cada uno para decir cual "
    "tiene mejor recepcion."
)


def format_event(node: str, update: dict[str, Any]) -> str:
    """Render one graph update as a human-readable trace entry."""
    if node == "supervisor":
        return (
            f"[supervisor] decision {update['step_count']} -> {update['next_agent']}\n"
            f"    reasoning: {update['supervisor_reasoning']}\n"
            f"    instructions: {update['instructions'] or '(none)'}"
        )
    if node in ("researcher", "analyst"):
        contribution = update["contributions"][0]
        return f"[{node}] contributed (decision {contribution['step']}):\n{contribution['output']}"
    return f"[synthesizer] FINAL ANSWER:\n{update['final_answer']}"


def run(task: str) -> str:
    """Execute the orchestrator on ``task``, print the delegation trace and save it."""
    graph = build_graph()
    print(f"Model: {MODEL_NAME}\nTask: {task}\n")
    trace: list[str] = []
    final_answer = ""
    for event in graph.stream(
        initial_state(task),
        config={"recursion_limit": RECURSION_LIMIT},
        stream_mode="updates",
    ):
        for node, update in event.items():
            entry = format_event(node, update)
            print(entry + "\n")
            trace.append(entry)
            final_answer = update.get("final_answer", final_answer)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "last_run.md"
    header = f"# Delegation trace\n\n- Date: {datetime.now():%Y-%m-%d %H:%M}\n- Model: {MODEL_NAME}\n- Task: {task}\n\n"
    log_path.write_text(header + "\n\n".join(f"```\n{e}\n```" for e in trace), encoding="utf-8")
    print(f"Trace saved to {log_path}")
    return final_answer


if __name__ == "__main__":
    run(" ".join(sys.argv[1:]).strip() or DEFAULT_TASK)
