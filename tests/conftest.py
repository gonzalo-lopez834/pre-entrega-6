"""Test helpers: a scripted fake chat model that needs no API key."""

from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from pydantic import Field


class ScriptedLLM(GenericFakeChatModel):
    """Fake chat model replaying scripted replies and scripted supervisor decisions.

    ``messages`` feeds plain chat calls (specialists' ReAct loops and the synthesizer);
    ``decisions`` feeds ``with_structured_output`` calls (the supervisor).
    """

    decisions: list[Any] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedLLM":
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:
        queue = iter(self.decisions)
        return RunnableLambda(lambda _prompt: next(queue))


def tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    """An AI message that requests one tool call."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
