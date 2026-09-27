from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.agent.context import GraphContext
from src.api.deps import get_graph_context
from src.repositories import ConversationRepository, ResolutionRepository
from src.schemas.resolution import ResolutionRequest, ResolutionResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/{conversation_id}/resolution", response_model=ResolutionResponse)
async def record_resolution(
    conversation_id: str,
    body: ResolutionRequest,
    context: Annotated[GraphContext, Depends(get_graph_context)],
) -> ResolutionResponse:
    """The answer to "Did this solve your problem?". A "No" sends the customer's next message
    to a Human Agent (the widget sends that message straight after)."""
    customer = await context.legacy.crm.get_customer(body.account_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    async with context.session_factory() as session:
        await ResolutionRepository(session).record(
            conversation_id=conversation_id, account_id=body.account_id, resolved=body.resolved
        )
        conversation = await ConversationRepository(session).start(
            conversation_id, body.account_id, f"{customer.name.given} {customer.name.family}"
        )
        if not body.resolved:
            conversation.pending_handoff = True
        await session.commit()
    return ResolutionResponse(ok=True)
