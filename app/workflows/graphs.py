
import sqlite3

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from app.workflows.state import GraphState

from app.workflows.node import (
    contextualize_query,
    retrieve,
    grade_documents,
    rewrite_query,
    web_search,
    generate,
    evaluate_generation,
    grade_generation_v_documents_and_question,
)



# 1. DECIDE HOW TO HANDLE RETRIEVED DOCUMENTS


def decide_to_generate(state: GraphState):
    """
    Determines whether to:
    1. Generate using internal runbooks.
    2. Rewrite the query and retry retrieval.
    3. Fall back to Tavily web search.
    """

    if state.get("web_search") == "no":
        return "generate"

    # Retry internal retrieval once before web fallback.
    if state.get("retry_count", 0) < 1:
        return "rewrite_query"

    return "web_search"



# 2. CREATE STATE GRAPH


workflow = StateGraph(GraphState)


# 3. REGISTER NODES


workflow.add_node("contextualize", contextualize_query)
workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("rewrite_query", rewrite_query)
workflow.add_node("web_search", web_search)
workflow.add_node("generate", generate)

# New Self-RAG evaluation node
workflow.add_node("evaluate_generation", evaluate_generation)



# 4. DEFINE INITIAL WORKFLOW


workflow.set_entry_point("contextualize")

workflow.add_edge("contextualize", "retrieve")
workflow.add_edge("retrieve", "grade_documents")



# 5. ROUTE AFTER DOCUMENT GRADING


workflow.add_conditional_edges(
    "grade_documents",
    decide_to_generate,
    {
        "generate": "generate",
        "rewrite_query": "rewrite_query",
        "web_search": "web_search",
    },
)

workflow.add_edge("rewrite_query", "retrieve")
workflow.add_edge("web_search", "generate")



# 6. GENERATE -> EVALUATE


workflow.add_edge("generate", "evaluate_generation")



# 7. ROUTE AFTER SELF-RAG EVALUATION


workflow.add_conditional_edges(
    "evaluate_generation",
    grade_generation_v_documents_and_question,
    {
        "useful": END,

        # Failed quality checks get one bounded regeneration attempt.
        "not supported": "generate",
        "not useful": "generate",

        # Evaluation errors or exhausted retries stop the workflow.
        "needs_review": END,
    },
)



# 8. SQLITE CHECKPOINTING


conn = sqlite3.connect(
    "checkpoints.sqlite",
    check_same_thread=False
)

memory = SqliteSaver(conn)

app_workflow = workflow.compile(
    checkpointer=memory
)
