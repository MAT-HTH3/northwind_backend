from collections.abc import Callable

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableLambda

from src.agent.categorizer import Categorization
from src.agent.context import GraphContext
from src.legacy import get_legacy_systems

FAKE_REPLY = "fake reply"


def self_service(_messages: list[AnyMessage]) -> Categorization:
    return Categorization(is_self_service=True, category="Service", reason="fake")


class FakeLLM:
    """Stands in for Gemini.

    - `with_structured_output(...)` (the Categorizer) returns whatever `decide` builds from the
      messages, or raises if `decide` raises.
    - `bind_tools(...)` (the Auto-Resolver) returns the scripted `replies` in order, then a plain
      text reply.
    """

    def __init__(
        self,
        decide: Callable[[list[AnyMessage]], Categorization] = self_service,
        replies: list[AIMessage] | None = None,
    ):
        self.decide = decide
        self.replies = list(replies or [])
        self.calls: list[list[AnyMessage]] = []
        self.tool_calls: list[list[AnyMessage]] = []

    def with_structured_output(self, _schema):
        async def run(messages):
            self.calls.append(messages)
            return self.decide(messages)

        return RunnableLambda(run)

    def bind_tools(self, _tools):
        async def run(messages):
            self.tool_calls.append(messages)
            return self.replies.pop(0) if self.replies else AIMessage(FAKE_REPLY)

        return RunnableLambda(run)


def fake_context(session_factory, llm: FakeLLM | None = None) -> GraphContext:
    """A graph context with one fake standing in for both Gemini models."""
    llm = llm or FakeLLM()
    return GraphContext(
        session_factory=session_factory,
        legacy=get_legacy_systems(),
        categorizer_llm=llm,
        resolver_llm=llm,
    )
