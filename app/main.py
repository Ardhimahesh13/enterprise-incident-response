
import logging
import os
import tempfile
from pathlib import Path

import uvicorn

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool

from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.workflows.graphs import app_workflow
from app.ingestion.loader import ingest_pdf_runbook

from app.core.database import (
    init_db,
    log_audit_event,
    log_document_upload,
    get_audit_logs,
    get_ingested_documents,
)


# 1. APPLICATION CONFIGURATION


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB

init_db()

app = FastAPI(title="Enterprise Incident Response Copilot")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory="ui"), name="ui")



# 2. REQUEST SCHEMA


class ChatRequest(BaseModel):
    question: str
    thread_id: str = "INC-001"



# 3. SERVE FRONTEND

@app.get("/")
async def serve_ui():
    return FileResponse("ui/index.html")



# 4. CHAT API


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):

    try:
        config = {
            "configurable": {
                "thread_id": request.thread_id
            }
        }

        inputs = {
            "question": request.question,
            "messages": [
                HumanMessage(content=request.question)
            ],
        }

        # Run synchronous LangGraph execution in a worker thread.
        result = await run_in_threadpool(
            app_workflow.invoke,
            inputs,
            config=config
        )

        # Extract actual workflow results.
        final_answer = result.get("generation")

        if not final_answer:
            raise RuntimeError("Workflow did not generate an answer.")

        steps = result.get("steps_taken", [])
        execution_events = result.get("execution_events", [])

        source_type = result.get("source_type", "Unknown")
        sources = result.get("documents", [])

        evaluation_status = result.get(
            "evaluation_status",
            "not_run"
        )

        is_supported = result.get("is_supported")
        is_useful = result.get("is_useful")

        evaluation_error = result.get("evaluation_error")
        retrieval_errors = result.get(
            "retrieval_grading_errors",
            []
        )

        # Save audit information without inventing evaluation success.
        await run_in_threadpool(
            log_audit_event,
            thread_id=request.thread_id,
            user_query=request.question,
            rewritten_query=result.get(
                "question",
                request.question
            ),
            source_type=source_type,
            sources_used=sources,
            steps_taken=steps,
            final_answer=final_answer,
        )

        return {
            "answer": final_answer,

            "source_type": source_type,
            "sources": sources,

            "steps_taken": steps,
            "execution_events": execution_events,

            "evaluation_status": evaluation_status,
            "is_supported": is_supported,
            "is_useful": is_useful,

            "evaluation_error": evaluation_error,
            "retrieval_grading_errors": retrieval_errors,

            "generation_retry_count": result.get(
                "generation_retry_count",
                0
            ),

            "rewritten_query": result.get("question"),
            "thread_id": request.thread_id,
        }

    except Exception as e:

        logger.exception("Chat workflow execution failed")

        if isinstance(e, HTTPException):
            raise e

        raise HTTPException(
            status_code=500,
            detail="Incident workflow execution failed."
        )



# 5. PDF RUNBOOK UPLOAD API


@app.post("/api/upload")
async def upload_runbook(file: UploadFile = File(...)):

    temp_path = None

    try:
        # Validate filename and extension.
        original_filename = (file.filename or "").replace("\\", "/")
        safe_filename = Path(original_filename).name

        if not safe_filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are allowed."
            )

        # Create a unique temporary file.
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix="runbook_",
            suffix=".pdf"
        )

        os.close(file_descriptor)

        temp_path = Path(temp_name)

        total_size = 0
        first_chunk = True

        # Stream the uploaded file instead of reading everything at once.
        with open(temp_path, "wb") as buffer:

            while True:

                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="PDF exceeds the 20 MB upload limit."
                    )

                # Basic PDF signature validation.
                if first_chunk:

                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(
                            status_code=400,
                            detail="Uploaded file is not a valid PDF."
                        )

                    first_chunk = False

                buffer.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded PDF is empty."
            )

        # PDF ingestion is synchronous, so execute it in a worker thread.
        chunks_count = await run_in_threadpool(
            ingest_pdf_runbook,
            str(temp_path)
        ) or 0

        # Record successful ingestion.
        await run_in_threadpool(
            log_document_upload,
            safe_filename,
            chunks_count
        )

        return {
            "message": (
                f"Ingested {safe_filename} "
                f"({chunks_count} chunks) into Pinecone."
            ),
            "filename": safe_filename,
            "chunks": chunks_count,
        }

    except HTTPException:
        raise

    except Exception:

        logger.exception("Runbook PDF ingestion failed")

        raise HTTPException(
            status_code=500,
            detail="PDF ingestion failed."
        )

    finally:

        # Always clean up temporary files.
        if temp_path and temp_path.exists():
            temp_path.unlink()

        await file.close()



# 6. DOCUMENT LIST API


@app.get("/api/documents")
async def list_documents():

    documents = await run_in_threadpool(
        get_ingested_documents
    )

    return {
        "documents": documents
    }



# 7. AUDIT / HISTORY API


@app.get("/api/audit")
@app.get("/api/history")
async def list_audit_history():

    logs = await run_in_threadpool(
        get_audit_logs
    )

    return {
        "logs": logs
    }



# 8. APPLICATION ENTRY POINT


if __name__ == "__main__":

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
