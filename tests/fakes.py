from collections.abc import Callable

from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableLambda

from src.agent.categorizer import Categorization


def self_service(_messages: list[AnyMessage]) -> Categorization:
    return Categorization(is_self_service=True, category="General enquiry", reason="fake")


class FakeLLM:
    """Stands in for Gemini: `with_structured_output(...)` returns whatever `decide` builds
    from the messages it was sent (or raises, if `decide` raises)."""

    def __init__(self, decide: Callable[[list[AnyMessage]], Categorization] = self_service):
        self.decide = decide
        self.calls: list[list[AnyMessage]] = []

    def with_structured_output(self, _schema):
        async def run(messages):
            self.calls.append(messages)
            return self.decide(messages)

        return RunnableLambda(run)
