import json
import logging
from datetime import datetime, timezone

from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_tavily import TavilySearch

from app.core.config import settings
from app.workflows.state import GraphState
from app.ingestion.loader import setup_pinecone_index

# 1. INITIALIZE EXISTING SERVICES

# Ensure Pinecone index exists on startup
setup_pinecone_index()

# Standard LLM for generation
llm = ChatGroq(
    temperature=0,
    groq_api_key=settings.GROQ_API_KEY,
    model_name="openai/gpt-oss-120b"
)

# Explicit JSON-mode LLM to bypass BadRequestError during strict evaluation
json_llm = ChatGroq(
    temperature=0,
    groq_api_key=settings.GROQ_API_KEY,
    model_name="openai/gpt-oss-120b",
    model_kwargs={"response_format": {"type": "json_object"}}
)

embeddings = HuggingFaceEmbeddings(
    model_name=settings.EMBEDDING_MODEL
)

vectorstore = PineconeVectorStore(
    index_name=settings.PINECONE_INDEX_NAME,
    embedding=embeddings,
    pinecone_api_key=settings.PINECONE_API_KEY
)

retriever = vectorstore.as_retriever(
    search_kwargs={"k": 4}
)

web_search_tool = TavilySearch(
    max_results=3,
    tavily_api_key=settings.TAVILY_API_KEY
)


# 2. EXECUTION TRACKING HELPERS

def record_execution(state, node_name, status, details=None):
    """
    Records one workflow event in a structured format.
    """
    events = list(state.get("execution_events", []))
    steps = list(state.get("steps_taken", []))

    event = {
        "node": node_name,
        "status": status,
        "details": details or "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    events.append(event)
    steps.append(f"{node_name}: {status}")

    return {
        "execution_events": events,
        "steps_taken": steps
    }


def get_binary_score(response_text: str) -> bool:
    """
    Safely parses JSON grader responses without relying on brittle Pydantic models.
    """
    try:
        data = json.loads(response_text)
        score = str(data.get("binary_score", "yes")).strip().lower()
        return score == "yes"
    except Exception:
        # Fallback regex-style check if JSON loads fail
        return "yes" in response_text.lower()


# 3. CONTEXTUALIZE QUERY

def contextualize_query(state: GraphState):
    """Rewrites follow-up questions using conversation history."""
    question = state["question"]
    messages = state.get("messages", [])

    result = record_execution(
        state,
        "Contextualize Query",
        "started"
    )

    if len(messages) > 1:
        history_str = "\n".join(
            [f"{m.type}: {m.content}" for m in messages[-4:-1]]
        )

        prompt = f"""
        Given the recent incident conversation history and the latest
        user follow-up question, rewrite the follow-up question into
        a standalone technical search query.

        Do NOT answer it.

        History:
        {history_str}

        Follow-up Question: {question}

        Standalone Query:
        """
        standalone = llm.invoke(prompt).content.strip()
    else:
        standalone = question

    result = record_execution(
        {**state, **result},
        "Contextualize Query",
        "completed",
        "Query is ready for retrieval"
    )

    return {
        **result,
        "question": standalone,
        "original_question": question,
        "retry_count": 0,
        "generation_retry_count": 0,
        "is_supported": None,
        "is_useful": None,
        "evaluation_status": "pending",
        "evaluation_error": None
    }


# 4. RETRIEVE DOCUMENTS FROM PINECONE

def retrieve(state: GraphState):
    """Retrieves and deduplicates relevant runbook chunks from Pinecone."""
    print("--- NODE: RETRIEVE FROM PINECONE ---")

    question = state["question"]
    docs = retriever.invoke(question)

    seen = set()
    doc_texts = []
    
    # Deduplicate chunks to prevent identical Sources in the UI
    for d in docs:
        text = f"[Runbook Page {d.metadata.get('page', 'N/A')}] {d.page_content}"
        if text not in seen:
            seen.add(text)
            doc_texts.append(text)

    result = record_execution(
        state,
        "Pinecone Vector Search",
        "completed",
        f"Retrieved {len(doc_texts)} unique documents"
    )

    return {
        **result,
        "documents": doc_texts,
        "source_type": "Internal Runbooks (Pinecone)"
    }


# 5. GRADE DOCUMENT RELEVANCE

def grade_documents(state: GraphState):
    """Checks whether retrieved documents are relevant to the incident using JSON-mode LLM."""
    print("--- NODE: GRADE DOCUMENT RELEVANCE ---")

    question = state["question"]
    documents = state.get("documents", [])

    filtered_docs = []
    grading_errors = []

    for index, doc in enumerate(documents):
        prompt = f"""
        You are an SRE relevance grader. Assess whether the retrieved runbook snippet contains information relevant to the incident.
        Respond ONLY in valid JSON with a single key "binary_score" set to "yes" or "no".

        Retrieved snippet:
        {doc[:1500]}

        Incident Query:
        {question}
        """

        try:
            score_res = json_llm.invoke(prompt)
            if get_binary_score(score_res.content):
                filtered_docs.append(doc)
        except Exception as exc:
            grading_errors.append(f"Document {index + 1}: {type(exc).__name__}")

    web_search = "no" if filtered_docs else "yes"
    status = "completed" if not grading_errors else "completed_with_errors"

    result = record_execution(
        state,
        "Grade Document Relevance",
        status,
        f"{len(filtered_docs)} relevant documents retained; {len(grading_errors)} errors"
    )

    return {
        **result,
        "documents": filtered_docs,
        "web_search": web_search,
        "retrieval_grading_errors": grading_errors
    }


# 6. REWRITE QUERY

def rewrite_query(state: GraphState):
    """Rewrites the query to improve retrieval."""
    print("--- NODE: REWRITE QUERY ---")

    question = state["question"]
    retry_count = state.get("retry_count", 0) + 1

    prompt = f"""
    You are a cloud infrastructure search optimizer.
    Rewrite the following incident query to be clearer,
    more specific, and better suited for technical documentation search.
    Output ONLY the rewritten query.

    Original query:
    {question}
    """
    better_question = llm.invoke(prompt).content.strip()

    result = record_execution(
        state,
        "Rewrite Query",
        "completed",
        f"Retrieval rewrite attempt {retry_count}"
    )

    return {
        **result,
        "question": better_question,
        "retry_count": retry_count
    }


# 7. TAVILY WEB SEARCH FALLBACK

def web_search(state: GraphState):
    """Uses Tavily when internal runbooks do not provide relevant evidence."""
    print("--- NODE: TAVILY WEB SEARCH FALLBACK ---")

    question = state["question"]
    results = web_search_tool.invoke({"query": question})

    web_docs = []
    for result in results:
        if isinstance(result, dict):
            web_docs.append(f"[Web Source: {result.get('url', 'External')}] {result.get('content', '')}")
        else:
            web_docs.append(str(result))

    execution = record_execution(
        state,
        "Tavily Web Search",
        "completed",
        f"Retrieved {len(web_docs)} web results"
    )

    return {
        **execution,
        "documents": web_docs,
        "source_type": "External Web Search (Tavily)"
    }


# 8. GENERATE INCIDENT RESPONSE

def generate(state: GraphState):
    """Generates an incident response using evidence and evaluation feedback."""
    print("--- NODE: GENERATE RESPONSE ---")

    question = state["original_question"]
    documents = state.get("documents", [])

    evaluation_status = state.get("evaluation_status", "pending")
    retry_count = state.get("generation_retry_count", 0)

    context = "\n\n---\n\n".join(documents) if documents else "No relevant documents found."
    feedback = ""

    if evaluation_status == "not_supported":
        feedback = """IMPORTANT: Your previous answer failed the grounding evaluation. Remove unsupported claims and use only information supported by the provided evidence."""
    elif evaluation_status == "not_useful":
        feedback = """IMPORTANT: Your previous answer failed the usefulness evaluation. Make the troubleshooting steps more relevant, specific, and actionable for the incident."""

    prompt = f"""
    You are a Senior Site Reliability Engineer (SRE) Incident Response Copilot.
    Analyze the incident query and provide an actionable troubleshooting guide grounded STRICTLY in the provided evidence.

    {feedback}

    Structure your response with:
    1. Root Cause Analysis
    2. Immediate Triage & Diagnostic Commands
    3. Resolution Steps
    4. Verification

    If evidence is insufficient, explicitly state what is missing. Never invent commands or unsupported technical facts.

    Evidence:
    {context}

    Incident Query:
    {question}
    """
    response = llm.invoke(prompt)

    result = record_execution(
        state,
        "Generate Grounded Response",
        "completed",
        f"Generation attempt {retry_count + 1}"
    )

    return {
        **result,
        "generation": response.content
    }


# 9. SELF-RAG EVALUATION NODE

def evaluate_generation(state: GraphState):
    """Evaluates the generated answer securely via JSON LLM bypassing 400 Bad Requests."""
    print("--- NODE: SELF-RAG EVALUATION ---")

    question = state["original_question"]
    documents = state.get("documents", [])
    generation = state.get("generation", "")

    # Trim to avoid exceeding payload limits
    context = "\n\n".join(documents)[:4000]
    generation_text = generation[:2500]

    is_supported = None
    is_useful = None
    evaluation_errors = []

    # IsSUP: Grounding / hallucination check
    try:
        sup_prompt = f"""
        You are a strict fact-checker. Verify if the Generated Answer is grounded in and supported by the Facts.
        Respond ONLY in valid JSON with a single key "binary_score" set to "yes" or "no".

        Facts:
        {context}

        Generated Answer:
        {generation_text}
        """
        sup_result = json_llm.invoke(sup_prompt)
        is_supported = get_binary_score(sup_result.content)
    except Exception as exc:
        evaluation_errors.append(f"IsSUP evaluation failed: {type(exc).__name__}")

    # IsUSE: Answer usefulness check
    try:
        use_prompt = f"""
        You are an SRE reviewer. Verify if the Generated Answer provides useful, actionable troubleshooting steps for the Question.
        Respond ONLY in valid JSON with a single key "binary_score" set to "yes" or "no".

        Question:
        {question}

        Generated Answer:
        {generation_text}
        """
        use_result = json_llm.invoke(use_prompt)
        is_useful = get_binary_score(use_result.content)
    except Exception as exc:
        logging.exception("IsUSE evaluation failed")
        evaluation_errors.append(f"IsUSE evaluation failed: {type(exc).__name__}: {str(exc)}")

    # Determine status
    if evaluation_errors:
        evaluation_status = "error"
    elif is_supported is False:
        evaluation_status = "not_supported"
    elif is_useful is False:
        evaluation_status = "not_useful"
    else:
        evaluation_status = "passed"

    generation_retry_count = state.get("generation_retry_count", 0)
    if evaluation_status in {"not_supported", "not_useful"}:
        generation_retry_count += 1

    details = f"IsSUP: {is_supported}; IsUSE: {is_useful}; Evaluation: {evaluation_status}"

    result = record_execution(
        state,
        "Self-RAG Quality Evaluation",
        evaluation_status,
        details
    )

    return {
        **result,
        "is_supported": is_supported,
        "is_useful": is_useful,
        "evaluation_status": evaluation_status,
        "evaluation_error": evaluation_errors or None,
        "generation_retry_count": generation_retry_count
    }


# 10. ROUTE AFTER EVALUATION

MAX_GENERATION_RETRIES = 1

def grade_generation_v_documents_and_question(state: GraphState):
    """Routes the workflow using the results stored by evaluate_generation()."""
    print("--- EDGE: ROUTE AFTER SELF-RAG EVALUATION ---")

    evaluation_status = state.get("evaluation_status", "error")
    retry_count = state.get("generation_retry_count", 0)

    if evaluation_status == "passed":
        print("--- DECISION: GROUNDED AND USEFUL ---")
        return "useful"

    if evaluation_status == "error":
        print("--- DECISION: EVALUATION ERROR -> REVIEW ---")
        return "needs_review"

    if retry_count > MAX_GENERATION_RETRIES:
        print("--- DECISION: RETRY LIMIT REACHED -> REVIEW ---")
        return "needs_review"

    if evaluation_status == "not_supported":
        print("--- DECISION: ANSWER NOT GROUNDED -> RETRY ---")
        return "not supported"

    if evaluation_status == "not_useful":
        print("--- DECISION: ANSWER NOT USEFUL -> RETRY ---")
        return "not useful"

    return "needs_review"