
from typing import TypedDict, List, Annotated, NotRequired, Literal
from langgraph.graph.message import add_messages


class ExecutionEvent(TypedDict):
    node: str
    status: str
    details: str
    timestamp: str


class GraphState(TypedDict):

    # Conversation inputs
    messages: Annotated[list, add_messages]
    question: str
    original_question: NotRequired[str]

    # LLM response
    generation: NotRequired[str]

    # Retrieval information
    web_search: NotRequired[str]
    source_type: NotRequired[str]
    documents: NotRequired[List[str]]

    # Retry counters
    retry_count: NotRequired[int]
    generation_retry_count: NotRequired[int]

    # Existing execution tracking
    steps_taken: NotRequired[List[str]]

    # New structured execution tracking
    execution_events: NotRequired[List[ExecutionEvent]]

    # Self-RAG evaluation results
    is_supported: NotRequired[bool | None]
    is_useful: NotRequired[bool | None]

    evaluation_status: NotRequired[
        Literal[
            "pending",
            "passed",
            "not_supported",
            "not_useful",
            "error"
        ]
    ]

    evaluation_error: NotRequired[List[str] | None]

    # Document relevance grading errors
    retrieval_grading_errors: NotRequired[List[str]]
