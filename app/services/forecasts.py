"""전망치 조회 서비스.

전망은 '실측이 아직 없는 가장 가까운 기간' 을 보여줘야 의미가 있다.
이미 발표된 달의 나우캐스팅 값을 예상치라고 붙여두면 오히려 혼란스럽다.
"""
from __future__ import annotations

from ..db import query, query_one


def next_for(code: str) -> dict | None:
    """해당 지표의 '다음 발표 예상치'.

    실측 최신 관측일보다 뒤 기간 중 가장 이른 월별 전망을 고른다.
    """
    latest = query_one(
        "SELECT MAX(obs_date) AS d FROM observations WHERE indicator_code = ?",
        (code,),
    )
    after = (latest["d"] if latest and latest["d"] else "1900-01-01")
    row = query_one(
        """SELECT target_period, value, source, as_of, note
           FROM forecasts
           WHERE indicator_code = ? AND horizon = 'month' AND target_period > ?
           ORDER BY target_period LIMIT 1""",
        (code, after),
    )
    return dict(row) if row else None


def yearly_for(code: str) -> list[dict]:
    """연도별 공식 전망(FOMC SEP 등)."""
    return [dict(r) for r in query(
        """SELECT target_period, value, source, note FROM forecasts
           WHERE indicator_code = ? AND horizon = 'year'
           ORDER BY target_period""",
        (code,),
    )]


def all_next() -> dict[str, dict]:
    """지표코드 → 다음 발표 예상치."""
    codes = [r["indicator_code"] for r in query(
        "SELECT DISTINCT indicator_code FROM forecasts WHERE horizon = 'month'")]
    out = {}
    for code in codes:
        fc = next_for(code)
        if fc:
            out[code] = fc
    return out


def yearly_table() -> list[dict]:
    """연도별 전망 전체 — 스냅샷/대시보드 표시용."""
    rows = query(
        """SELECT f.indicator_code, i.name_ko, f.target_period, f.value,
                  f.source, f.note
           FROM forecasts f LEFT JOIN indicators i ON i.code = f.indicator_code
           WHERE f.horizon = 'year'
           ORDER BY f.indicator_code, f.target_period"""
    )
    return [dict(r) for r in rows]
