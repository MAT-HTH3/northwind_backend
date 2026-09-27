"""ADR 0003: the model sees only the customer's words, its own replies and tool statuses.

Runs a whole conversation (bill question with the tool, an accepted reading, an implausible
reading handed off, held message, close, follow-up) and checks nothing from the account reached
either model.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.categorizer import Categorization, MeterReadingMention
from src.agent.graph import build_graph
from src.agent.turns import close_input, thread_config, turn_input
from src.models import Service
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"

# Values from the fixtures, the database and code-written replies. None may reach the model.
ACCOUNT_DATA = [
    ACCOUNT, "Sarah", "Whitfield", "sarah.whitfield", "07700", "0900001", "CT-00900001",
    "CT-88123", "INV-2609", "INV-2608", "169.6", "118.39", "120.82", "47,871", "47871",
    "48357", "1900012345678", "486 kWh", "NW-", "October", "Tuesday", "Standard Variable",
    "132.01", "342",
]  # fmt: skip


def decide(messages):
    last = next(m.text for m in reversed(messages) if isinstance(m, HumanMessage))
    value = next((int(word) for word in last.split() if word.isdigit()), None)
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=value) if value else None
    return Categorization(
        is_self_service=reading is None, category="Billing", reason="fake", meter_reading=reading
    )


def sent_text(message) -> str:
    """What a chat model integration actually sends: content, tool calls and name."""
    return json.dumps(
        [str(message.content), getattr(message, "tool_calls", None), message.name],
        ensure_ascii=False,
    )


async def test_nothing_from_the_account_reaches_the_model(session_factory):
    llm = FakeLLM(
        decide,
        replies=[
            AIMessage("", tool_calls=[{"id": "c1", "name": "show_bill_breakdown", "args": {}}]),
            AIMessage("Here's your latest bill."),
            AIMessage("It's on the bill card."),
        ],
    )
    context = fake_context(session_factory, llm)
    graph, config = build_graph(InMemorySaver()), thread_config("c1")

    async def say(message):
        payload = await turn_input(graph, conversation_id="c1", account_id=ACCOUNT, message=message)
        return await graph.ainvoke(payload, config, context=context)

    await say("Why is my bill so high?")
    await say("My meter says 48213")  # plausible: accepted and re-priced
    handed_off = await say("Sorry, it actually says 41213")  # implausible: a Human Agent
    await say("Any update?")
    await graph.ainvoke(close_input("bill_corrected"), config, context=context)
    await say("Thanks, when is my payment due?")

    # The conversation did carry account data: it reached the customer, just not the model.
    assert handed_off["case_id"] in handed_off["messages"][-1].text

    sent = [sent_text(m) for call in llm.calls + llm.tool_calls for m in call]
    assert len(llm.calls) == 4 and len(llm.tool_calls) == 3
    leaks = {value for value in ACCOUNT_DATA for text in sent if value in text}
    assert leaks == set()
    assert any("48213" in text for text in sent)  # the customer's own words are fine
