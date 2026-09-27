"""The agent desk's API (/api/agent/*). Records only: the desk works out triage and statistics
itself, and nothing here calls the model."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.graph.state import CompiledStateGraph

from src.agent.context import GraphContext
from src.agent.turns import close_input, is_held, thread_config
from src.api.deps import get_graph, get_graph_context
from src.desk import records
from src.desk.transcript import transcript
from src.history import UnknownCustomerError, build_history
from src.models import CaseStatus, Urgency
from src.models.types import utcnow
from src.repositories import CaseChanges, ConversationRepository, SupportCaseRepository
from src.schemas.agent import (
    AgentCase,
    CaseDetail,
    CaseUpdate,
    ConversationDetail,
    FeedbackEntry,
    FeedbackRequest,
    QueueFeedback,
    QueueSnapshot,
)

router = APIRouter(prefix="/agent", tags=["agent desk"])

CLOSED_WINDOW = timedelta(days=90)
RECENT_WINDOW = timedelta(days=30)

Graph = Annotated[CompiledStateGraph, Depends(get_graph)]
Context = Annotated[GraphContext, Depends(get_graph_context)]


@router.get("/queue", response_model=QueueSnapshot)
async def queue(context: Context) -> QueueSnapshot:
    now = utcnow()
    async with context.session_factory() as session:
        cases = await SupportCaseRepository(session).list_for_queue(now - CLOSED_WINDOW)
        feedback = await SupportCaseRepository(session).feedback_since(now - RECENT_WINDOW)
        conversations_repo = ConversationRepository(session)
        conversations = [
            records.assistant_conversation(c, await conversations_repo.outcome(c.id))
            for c in await conversations_repo.list_since(now - RECENT_WINDOW)
        ]
    return QueueSnapshot(
        cases=[records.agent_case(c) for c in cases],
        conversations=conversations,
        feedback=[
            QueueFeedback(case_id=f.case_id, **records.feedback_entry(f).model_dump())
            for f in feedback
        ],
        generated_at=now,
    )


@router.get("/cases/{case_id}", response_model=CaseDetail)
async def case_detail(case_id: str, graph: Graph, context: Context) -> CaseDetail:
    async with context.session_factory() as session:
        case = await _get_case(SupportCaseRepository(session), case_id)
        conversation_ids = [link.conversation_id for link in case.conversations]
        detail = CaseDetail(
            case=records.agent_case(case),
            transcript=None,
            account=None,
            timeline=records.timeline(case),
            feedback=[records.feedback_entry(f) for f in case.feedback],
        )
    if conversation_ids:  # chat cases: every conversation the case gathered, in order
        entries = [e for cid in conversation_ids for e in await transcript(graph, cid)]
        detail.transcript = sorted(entries, key=lambda e: e.at)
    try:
        history = await build_history(case.account_id, context.legacy, context.session_factory)
        detail.account = records.account_snapshot(history)
    except UnknownCustomerError:
        pass
    return detail


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def conversation_detail(
    conversation_id: str, graph: Graph, context: Context
) -> ConversationDetail:
    async with context.session_factory() as session:
        repo = ConversationRepository(session)
        conversation = await repo.get(conversation_id)
        if conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        summary = records.assistant_conversation(conversation, await repo.outcome(conversation_id))
    return ConversationDetail(
        conversation=summary, transcript=await transcript(graph, conversation_id)
    )


@router.patch("/cases/{case_id}", response_model=AgentCase)
async def update_case(case_id: str, body: CaseUpdate, graph: Graph, context: Context) -> AgentCase:
    """Resolving a case releases every conversation it was holding (ADR 0001)."""
    sent = body.model_fields_set
    changes = CaseChanges(
        status=CaseStatus(body.status) if body.status else None,
        assignee=body.assignee,
        priority_override=Urgency(body.priority_override) if body.priority_override else None,
        resolution=body.resolution,
        clear={
            f for f in ("assignee", "priority_override") if f in sent and getattr(body, f) is None
        },
    )
    async with context.session_factory() as session:
        repo = SupportCaseRepository(session)
        case = await _get_case(repo, case_id)
        released = await repo.update(case, changes, actor=body.assignee or "Human Agent")
        outcome = case.outcome
        await session.commit()
        result = records.agent_case(case)
    for conversation_id in released:
        if await is_held(graph, conversation_id):
            await graph.ainvoke(
                close_input(outcome or "other"), thread_config(conversation_id), context=context
            )
    return result


@router.post("/cases/{case_id}/feedback", response_model=FeedbackEntry)
async def add_feedback(case_id: str, body: FeedbackRequest, context: Context) -> FeedbackEntry:
    """Stored verbatim for Human Agents; never summarised and never sent to the model."""
    async with context.session_factory() as session:
        repo = SupportCaseRepository(session)
        case = await _get_case(repo, case_id)
        entry = await repo.add_feedback(case, tags=body.tags, note=body.note, author=body.author)
        await session.commit()
        return records.feedback_entry(entry)


async def _get_case(repo: SupportCaseRepository, case_id: str):
    case = await repo.get(case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case
