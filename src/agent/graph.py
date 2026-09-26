"""The support graph. Runs once per chat message; thread_id = conversation_id.

START → Analyzer → Categorizer → Router ─self-service→ Auto-Resolver → END
                                        └─hand-off──→ Unified Desktop → Wait ⏸
Wait ─customer message→ Acknowledge → Wait ⏸
Wait ─Case Outcome────→ Close → END
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent import nodes
from src.agent.context import GraphContext
from src.agent.state import SupportState


def build_graph(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(SupportState, context_schema=GraphContext)

    graph.add_node("analyzer", nodes.analyzer)
    graph.add_node("categorizer", nodes.categorizer)
    graph.add_node("auto_resolver", nodes.auto_resolver)
    graph.add_node("unified_desktop", nodes.unified_desktop)
    graph.add_node("wait", nodes.wait)
    graph.add_node("acknowledge", nodes.acknowledge)
    graph.add_node("close", nodes.close)

    graph.add_edge(START, "analyzer")
    graph.add_edge("analyzer", "categorizer")
    graph.add_conditional_edges("categorizer", nodes.route_after_categorizer)
    graph.add_edge("auto_resolver", END)
    graph.add_edge("unified_desktop", "wait")
    graph.add_edge("acknowledge", "wait")
    graph.add_edge("close", END)

    return graph.compile(checkpointer=checkpointer)
