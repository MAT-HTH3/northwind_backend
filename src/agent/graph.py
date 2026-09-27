"""The support graph. Runs once per chat message; thread_id = conversation_id.

START → Analyzer → Categorizer → Router ─plausible reading→ Accept reading → END
                                        ├─self-service─────→ Auto-Resolver ⇄ tools → END
                                        └─hand-off─────────→ Unified Desktop → Wait ⏸
Wait ─customer message→ Acknowledge → Wait ⏸
Wait ─Case Outcome────→ Close → END
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.agent import nodes
from src.agent.bill_breakdown import BillNotFoundError
from src.agent.context import GraphContext
from src.agent.state import SupportState
from src.agent.tools import AUTO_RESOLVER_TOOLS


def build_graph(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(SupportState, context_schema=GraphContext)

    graph.add_node("analyzer", nodes.analyzer)
    graph.add_node("categorizer", nodes.categorizer)
    graph.add_node("accept_reading", nodes.accept_reading)
    graph.add_node("auto_resolver", nodes.auto_resolver)
    # A missing bill goes back to Gemini as the tool result (listing the real bills), not a crash.
    graph.add_node(
        "resolver_tools", ToolNode(AUTO_RESOLVER_TOOLS, handle_tool_errors=BillNotFoundError)
    )
    graph.add_node("unified_desktop", nodes.unified_desktop)
    graph.add_node("wait", nodes.wait)
    graph.add_node("acknowledge", nodes.acknowledge)
    graph.add_node("close", nodes.close)

    graph.add_edge(START, "analyzer")
    graph.add_edge("analyzer", "categorizer")
    graph.add_conditional_edges("categorizer", nodes.route_after_categorizer)
    graph.add_conditional_edges("auto_resolver", nodes.route_after_auto_resolver)
    graph.add_edge("resolver_tools", "auto_resolver")
    graph.add_edge("accept_reading", END)
    graph.add_edge("unified_desktop", "wait")
    graph.add_edge("acknowledge", "wait")
    graph.add_edge("close", END)

    return graph.compile(checkpointer=checkpointer)
