from src.config import MAX_STEPS
from src.state import merge_visits
from src.supervisor import SupervisorDecision, apply_guardrails


def decide(next_: str, instructions: str = "do it") -> SupervisorDecision:
    return SupervisorDecision(reasoning="r", next=next_, instructions=instructions)  # type: ignore[arg-type]


def test_normal_dispatch_keeps_instructions() -> None:
    routing = apply_guardrails(decide("researcher"), step_count=0, visits={}, contributed=set())
    assert (routing.next_agent, routing.instructions, routing.note) == ("researcher", "do it", "")


def test_finish_rejected_until_both_domains_contributed() -> None:
    routing = apply_guardrails(decide("FINISH", ""), step_count=1, visits={"researcher": 1}, contributed={"researcher"})
    assert routing.next_agent == "analyst" and "FINISH rejected" in routing.note


def test_finish_accepted_when_both_contributed() -> None:
    routing = apply_guardrails(
        decide("FINISH", ""), step_count=2, visits={"researcher": 1, "analyst": 1}, contributed={"researcher", "analyst"}
    )
    assert routing.next_agent == "synthesizer"


def test_analyst_blocked_before_research() -> None:
    routing = apply_guardrails(decide("analyst"), step_count=0, visits={}, contributed=set())
    assert routing.next_agent == "researcher" and routing.instructions == ""


def test_refinement_limit_forces_synthesis() -> None:
    routing = apply_guardrails(
        decide("researcher"),
        step_count=3,
        visits={"researcher": 2, "analyst": 1},
        contributed={"researcher", "analyst"},
    )
    assert routing.next_agent == "synthesizer"


def test_refinement_limit_reroutes_to_missing_specialist() -> None:
    routing = apply_guardrails(decide("researcher"), step_count=2, visits={"researcher": 2}, contributed={"researcher"})
    assert routing.next_agent == "analyst"


def test_step_budget_forces_synthesis() -> None:
    routing = apply_guardrails(decide("researcher"), step_count=MAX_STEPS, visits={}, contributed=set())
    assert routing.next_agent == "synthesizer"


def test_visits_reducer_merges() -> None:
    assert merge_visits({"researcher": 1}, {"analyst": 1}) == {"researcher": 1, "analyst": 1}
    assert merge_visits(None, {"a": 1}) == {"a": 1}
