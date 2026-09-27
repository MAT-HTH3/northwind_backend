from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage


def recent_messages(messages: list[AnyMessage], limit: int) -> list[AnyMessage]:
    """At most `limit` recent messages, starting at a customer message.

    Starting anywhere else can leave a tool result without the tool call that produced it,
    which Gemini rejects. If no customer message falls inside the limit (a long tool loop), the
    window stretches back to the latest one, so the message being answered is always included.
    """
    if len(messages) <= limit:
        return messages
    human = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    start = next((i for i in human if i >= len(messages) - limit), human[-1] if human else 0)
    return messages[start:]


def transcript_text(messages: list[AnyMessage]) -> str:
    """The conversation as plain text, for tasks about a transcript (e.g. a case summary).

    Gemini returns an empty reply when such a task is sent as a chat continuation that
    contains tool calls, so the transcript goes in as text instead.
    """
    lines = []
    for message in messages:
        if isinstance(message, HumanMessage):
            lines.append(f"Customer: {message.text}")
        elif isinstance(message, AIMessage):
            lines.extend(f"[AI Assistant showed {call['name']}]" for call in message.tool_calls)
            if message.text:
                lines.append(f"AI Assistant: {message.text}")
        elif isinstance(message, ToolMessage):
            continue  # its data is in the Unified Customer History already
    return "\n".join(lines)


WRITTEN_BY_CODE = "written_by_code"  # AIMessage.additional_kwargs: what the model sees instead
CODE_REPLY_PLACEHOLDER = (
    "The assistant replied with account details shown on the customer's screen."
)


def written_by_code(text: str, *, summary: str, **additional_kwargs) -> AIMessage:
    """A reply built by code from account records. It may contain case numbers, dates or
    amounts, so the model never sees it (ADR 0003). It sees `summary` instead: what happened,
    with no data in it, so it still knows the conversation has moved on (e.g. that a person was
    already arranged)."""
    return AIMessage(text, additional_kwargs={WRITTEN_BY_CODE: summary, **additional_kwargs})


def for_model(messages: list[AnyMessage]) -> list[AnyMessage]:
    """What the model may see (ADR 0003): the customer's words, the model's own general
    replies and tool statuses. Replies written by code become their data-free summary."""
    return [
        AIMessage(f"[{_summary(m)}]") if isinstance(m, AIMessage) and _summary(m) else m
        for m in messages
    ]


def _summary(message: AIMessage) -> str | None:
    flag = message.additional_kwargs.get(WRITTEN_BY_CODE)
    if not flag:
        return None
    return (
        flag if isinstance(flag, str) else CODE_REPLY_PLACEHOLDER
    )  # older checkpoints stored True
