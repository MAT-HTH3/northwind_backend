from fastapi import Request
from langgraph.graph.state import CompiledStateGraph

from src.agent.context import GraphContext


def get_graph(request: Request) -> CompiledStateGraph:
    return request.app.state.graph


def get_graph_context(request: Request) -> GraphContext:
    return request.app.state.graph_context
