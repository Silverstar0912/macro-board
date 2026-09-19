"""발언 피드 서비스."""
from __future__ import annotations

from ..db import query


def feed(limit: int = 40, tone: str | None = None, org: str | None = None) -> list[dict]:
    sql = "SELECT * FROM speeches WHERE 1=1"
    params: list = []
    if tone:
        sql += " AND tone = ?"
        params.append(tone)
    if org:
        sql += " AND org = ?"
        params.append(org)
    sql += " ORDER BY published_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in query(sql, params)]


def tone_stats(days: int = 30) -> dict:
    """최근 발언의 매파/비둘기파 분포 — 정책 기조 온도계."""
    rows = query(
        """SELECT tone, COUNT(*) AS n FROM speeches
           WHERE published_at >= date('now', ?) GROUP BY tone""",
        (f"-{days} days",),
    )
    stats = {"hawkish": 0, "dovish": 0, "neutral": 0}
    for r in rows:
        if r["tone"] in stats:
            stats[r["tone"]] = r["n"]
    return stats
