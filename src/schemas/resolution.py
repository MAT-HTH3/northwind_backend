"""POST /api/conversations/{conversation_id}/resolution. Shape defined in the frontend's
docs/api-contract.md."""

from pydantic import BaseModel, Field


class ResolutionRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=32)
    resolved: bool


class ResolutionResponse(BaseModel):
    ok: bool
