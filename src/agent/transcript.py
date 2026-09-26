from langchain_core.messages import AnyMessage, HumanMessage


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
