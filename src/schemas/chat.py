"""POST /api/chat request. Shape defined in the frontend's docs/api-contract.md."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=32)
    # The widget sends the whole history; with the checkpointer only the last user message matters.
    messages: list[ChatMessage] = Field(min_length=1)

    def latest_user_message(self) -> str | None:
        return next((m.content for m in reversed(self.messages) if m.role == "user"), None)
