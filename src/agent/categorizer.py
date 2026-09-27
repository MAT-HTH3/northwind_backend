"""The Categorizer: is this message a Self-service request or a Hand-off request?

Gemini classifies the conversation text alone: it never sees account records (ADR 0003). Code
then applies the rules the LLM may not overrule (ADR 0002 and the "No" answer to "Did this solve
your problem?") and keeps the subject consistent with the category.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agent.categories import FALLBACK, METER_READING, Category, Subject, subject_for
from src.agent.transcript import for_model, recent_messages
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
    subject: Subject = Field(
        default="Other service query",
        description="The case title that fits best. It must belong to the chosen category.",
    )
    reason: str = Field(description="One short sentence explaining the decision.")
    meter_reading: MeterReadingMention | None = Field(
        default=None,
        description="Only if the customer gives a reading from their meter display.",
    )
    disputed_amount: float | None = Field(
        default=None,
        description="Only if the customer states an amount of money they dispute, in pounds.",
    )
    case_status_request: bool = Field(
        default=False,
        description="True if the customer asks about a case, complaint or request they already "
        "made: its status, an update, or when someone will reply.",
    )


SYSTEM_PROMPT = """\
You triage messages for Northwind, a UK electricity and water supplier. Decide whether the \
AI Assistant can fully resolve the customer's LATEST message, or whether it needs a Human Agent. \
You only see the conversation; account details are handled elsewhere.

Self-service (is_self_service = true), the AI Assistant can resolve these:
- explaining a bill, its charges, or why it changed
- when a payment is due or how it is paid
- asking about an existing case or complaint (also set case_status_request = true)
- greetings, thanks and general questions about the account

Hand-off (is_self_service = false), these need a Human Agent:
- a physical repair or supply problem (no power, no water, leaks, damaged meter)
- a manual billing exception: refund, dispute, payment plan or arrangement, write-off
- the customer gives a meter reading
- the customer asks for a person, or says the AI Assistant has not solved their problem

Also:
- category and subject: the closest topic and case title, even for self-service messages.
- meter_reading: fill it only when the customer states the number on their meter display.
  Bill amounts, kWh on a bill, account numbers and phone numbers are not meter readings.
- disputed_amount: only a sum of money the customer says is wrong or wants back.
- reason: one short sentence.
"""


async def classify(llm: BaseChatModel, messages: list[AnyMessage]) -> Categorization:
    structured = llm.with_structured_output(Categorization)
    window = for_model(recent_messages(messages, TRANSCRIPT_WINDOW))
    return await structured.ainvoke([SystemMessage(SYSTEM_PROMPT), *window])


async def categorize(
    llm: BaseChatModel, messages: list[AnyMessage], *, force_handoff: bool
) -> Categorization:
    """Classify, then enforce the rules the LLM may not overrule:

    - a meter reading always goes to a Human Agent, in the Meter reading category (ADR 0002;
      #36 changes this to ADR 0004)
    - after the customer answers "No" (force_handoff), the message always goes to a Human Agent

    If Gemini fails while one of those rules applies, the hand-off still happens.
    """
    try:
        result = await classify(llm, messages)
    except Exception:
        if not force_handoff:
            raise
        logger.exception("Categorizer LLM failed; forcing hand-off with the fallback category")
        return Categorization(
            is_self_service=False,
            category=FALLBACK,
            subject="Asked for a person",
            reason="The customer said their problem was not solved.",
        )

    if result.meter_reading is not None:
        result = result.model_copy(
            update={
                "is_self_service": False,
                "category": METER_READING,
                "subject": "Reading needs checking",
            }
        )
    elif force_handoff:
        result = result.model_copy(update={"is_self_service": False})
    return result.model_copy(update={"subject": subject_for(result.category, result.subject)})
