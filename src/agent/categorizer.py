"""The Categorizer: is this message a Self-service request or a Hand-off request?

Gemini classifies; code then applies the rules the LLM may not overrule (ADR 0002 and the
"No" answer to "Did this solve your problem?").
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agent.categories import FALLBACK, METER_READING_REVIEW, Category
from src.history import UnifiedCustomerHistory
from src.models import Service

logger = logging.getLogger(__name__)

TRANSCRIPT_WINDOW = 12


class MeterReadingMention(BaseModel):
    service: Service = Field(description="Which meter the number is from.")
    value: int = Field(description="The number on the meter display, digits only.")


class Categorization(BaseModel):
    is_self_service: bool = Field(
        description="True if the AI Assistant can fully resolve the latest message itself."
    )
    category: Category = Field(description="The closest topic for the latest message.")
    reason: str = Field(description="One short sentence explaining the decision.")
    meter_reading: MeterReadingMention | None = Field(
        default=None,
        description="Only if the customer gives a reading from their meter display.",
    )


SYSTEM_PROMPT = """\
You triage messages for Northwind, a UK electricity and water supplier. Decide whether the \
AI Assistant can fully resolve the customer's LATEST message, or whether it needs a Human Agent.

Self-service (is_self_service = true), the AI Assistant can resolve these with the data below:
- explaining a bill, its charges, or why it changed
- when a payment is due or how it is paid
- the status of an existing Support Case
- greetings, thanks and general questions about the account

Hand-off (is_self_service = false), these need a Human Agent:
- a physical repair or supply problem (no power, no water, leaks, damaged meter)
- a manual billing exception: refund, dispute, payment plan or arrangement, write-off
- the customer gives a meter reading
- the customer asks for a person, or says the AI Assistant has not solved their problem

Also:
- category: the closest topic, even for self-service messages.
- meter_reading: fill it only when the customer states the number on their meter display.
  Bill amounts, kWh on a bill, account numbers and phone numbers are not meter readings.
- reason: one short sentence.

Everything known about this customer (Unified Customer History, JSON):
{history}
"""


async def classify(
    llm: BaseChatModel, messages: list[AnyMessage], history: UnifiedCustomerHistory
) -> Categorization:
    prompt = SystemMessage(SYSTEM_PROMPT.format(history=history.model_dump_json()))
    structured = llm.with_structured_output(Categorization)
    return await structured.ainvoke([prompt, *messages[-TRANSCRIPT_WINDOW:]])


async def categorize(
    llm: BaseChatModel,
    messages: list[AnyMessage],
    history: UnifiedCustomerHistory,
    *,
    force_handoff: bool,
) -> Categorization:
    """Classify, then enforce the rules the LLM may not overrule:

    - a meter reading always goes to a Human Agent, as a Meter reading review (ADR 0002)
    - after the customer answers "No" (force_handoff), the message always goes to a Human Agent

    If Gemini fails while one of those rules applies, the hand-off still happens.
    """
    try:
        result = await classify(llm, messages, history)
    except Exception:
        if not force_handoff:
            raise
        logger.exception("Categorizer LLM failed; forcing hand-off with the fallback category")
        return Categorization(
            is_self_service=False,
            category=FALLBACK,
            reason="The customer said their problem was not solved.",
        )

    if result.meter_reading is not None:
        return result.model_copy(
            update={"is_self_service": False, "category": METER_READING_REVIEW}
        )
    if force_handoff:
        return result.model_copy(update={"is_self_service": False})
    return result
