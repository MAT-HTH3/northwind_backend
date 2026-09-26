from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph

from src.agent.context import GraphContext
from src.api.deps import get_graph, get_graph_context
from src.api.streaming import stream_turn
from src.schemas.chat import ChatRequest

router = APIRouter(tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # stop nginx buffering the stream on the demo server
}


@router.post("/chat")
async def chat(
    body: ChatRequest,
    graph: Annotated[CompiledStateGraph, Depends(get_graph)],
    context: Annotated[GraphContext, Depends(get_graph_context)],
) -> StreamingResponse:
    message = body.latest_user_message()
    if message is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No user message to answer")
    if await context.legacy.crm.get_customer(body.account_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    return StreamingResponse(
        stream_turn(
            graph,
            context,
            conversation_id=body.conversation_id,
            account_id=body.account_id,
            message=message,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
