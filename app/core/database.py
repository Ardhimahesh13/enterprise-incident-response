import sqlite3
from datetime import datetime
from typing import List, Dict

DB_PATH = "incident_copilot.db"

def init_db() :
    """Creates tables for audit logs and ingested document tracking"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Audit logs table (matches Architecture: Simple Audit Logs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            user_query TEXT NOT NULL,
            rewritten_query TEXT,
            source_type TEXT NOT NULL,
            sources_used TEXT,
            steps_taken TEXT,
            final_answer TEXT NOT NULL
        )
    """)
    
    # Ingested runbooks metadata table (matches Architecture: /api/documents)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingested_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            chunks_count INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()

def log_audit_event(
    thread_id: str,
    user_query: str,
    rewritten_query: str,
    source_type: str,
    sources_used: List[str],
    steps_taken: List[str],
    final_answer: str
):
    """Records every incident investigation for compliance and UI history."""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_logs 
        (thread_id, timestamp, user_query, rewritten_query, source_type, sources_used, steps_taken, final_answer)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        thread_id,
        datetime.utcnow().isoformat() + "Z",
        user_query,
        rewritten_query,
        source_type,
        " | ".join(sources_used[:3]),
        " -> ".join(steps_taken),
        final_answer
    ))
    conn.commit()
    conn.close()

def log_document_upload(filename: str, chunks_count: int):
    """Tracks uploaded runbooks for the UI Document Manager."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ingested_documents (filename, chunks_count, uploaded_at)
        VALUES (?, ?, ?)
    """, (filename, chunks_count, datetime.utcnow().isoformat() + "Z"))
    conn.commit()
    conn.close()

def get_audit_logs(limit: int = 50) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_ingested_documents() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ingested_documents ORDER BY id DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows