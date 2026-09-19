"""연준 문서(회의록·성명) 조회 서비스."""
from __future__ import annotations

from ..db import query, query_one


def feed(limit: int = 10, doc_type: str | None = None,
         translated_only: bool = False) -> list[dict]:
    sql = """SELECT uid, doc_type, meeting_date, title, url, summary_ko,
                    tone, tone_reason, translated_at, length(body) AS body_len
             FROM documents WHERE 1=1"""
    params: list = []
    if doc_type:
        sql += " AND doc_type = ?"
        params.append(doc_type)
    if translated_only:
        sql += " AND summary_ko IS NOT NULL"
    sql += " ORDER BY meeting_date DESC, doc_type LIMIT ?"
    params.append(limit)
    return [dict(r) for r in query(sql, params)]


def latest_minutes() -> dict | None:
    row = query_one(
        """SELECT * FROM documents WHERE doc_type = 'minutes'
           AND summary_ko IS NOT NULL ORDER BY meeting_date DESC LIMIT 1""")
    return dict(row) if row else None


def get(uid: str) -> dict | None:
    row = query_one("SELECT * FROM documents WHERE uid = ?", (uid,))
    return dict(row) if row else None


def pending_count() -> int:
    row = query_one(
        """SELECT COUNT(*) AS n FROM documents
           WHERE summary_ko IS NULL AND length(body) > 500""")
    return int(row["n"]) if row else 0
