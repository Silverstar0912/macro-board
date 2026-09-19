"""지표 조회 서비스 — KPI 요약, 시계열, 수익률곡선."""
from __future__ import annotations

from datetime import date, timedelta

from ..collectors.treasury import CURVE_COLUMNS, CURVE_TENORS, curve_code
from ..db import query, query_one
from . import forecasts as fc_svc

RANGE_DAYS = {"1Y": 365, "3Y": 365 * 3, "5Y": 365 * 5, "10Y": 365 * 10, "MAX": 0}

# 일별 지표가 이 일수를 넘겨 멈춰 있으면 '지연' 으로 표시한다.
# 주말·공휴일이 겹치면 3일까지는 정상이므로 그보다 넉넉히 잡는다.
STALE_DAYS = 4


def _start_date(range_key: str) -> str:
    days = RANGE_DAYS.get(range_key.upper(), 365 * 5)
    if days == 0:
        return "1900-01-01"
    return (date.today() - timedelta(days=days)).isoformat()


def catalog() -> list[dict]:
    return [dict(r) for r in query(
        "SELECT * FROM indicators ORDER BY display_order, code")]


def summary() -> list[dict]:
    """카탈로그 전 지표의 최신값과 직전 관측 대비 변화량."""
    out: list[dict] = []
    for ind in query("SELECT * FROM indicators ORDER BY display_order, code"):
        rows = query(
            """SELECT obs_date, value FROM observations
               WHERE indicator_code = ? ORDER BY obs_date DESC LIMIT 2""",
            (ind["code"],),
        )
        item = dict(ind)
        if rows:
            item["latest_date"] = rows[0]["obs_date"]
            item["latest"] = rows[0]["value"]
            if len(rows) > 1:
                item["prev"] = rows[1]["value"]
                item["prev_date"] = rows[1]["obs_date"]
                item["change"] = rows[0]["value"] - rows[1]["value"]
            else:
                item["prev"] = item["change"] = None
            # 1년 전 대비 (같은 날짜가 없으면 그 이전 최근값)
            year_ago = query_one(
                """SELECT value FROM observations
                   WHERE indicator_code = ? AND obs_date <= ?
                   ORDER BY obs_date DESC LIMIT 1""",
                (ind["code"], (date.fromisoformat(rows[0]["obs_date"])
                               - timedelta(days=365)).isoformat()),
            )
            item["yoy_change"] = (rows[0]["value"] - year_ago["value"]) if year_ago else None
            item["has_data"] = True
            item["forecast"] = fc_svc.next_for(ind["code"])
            # 일별 지표가 오래 멈춰 있으면 옛 값을 오늘 값으로 오해하게 된다.
            # 화면에서 바로 보이도록 지연일수를 함께 실어 보낸다.
            gap = (date.today() - date.fromisoformat(rows[0]["obs_date"])).days
            item["lag_days"] = gap
            item["stale"] = bool(ind["frequency"] == "D" and gap > STALE_DAYS)
        else:
            item.update(latest=None, latest_date=None, prev=None, change=None,
                        yoy_change=None, has_data=False, forecast=None,
                        lag_days=None, stale=False)
        out.append(item)
    return out


def series(codes: list[str], range_key: str = "5Y") -> dict:
    start = _start_date(range_key)
    result: dict[str, dict] = {}
    for code in codes:
        meta = query_one("SELECT * FROM indicators WHERE code = ?", (code,))
        rows = query(
            """SELECT obs_date, value FROM observations
               WHERE indicator_code = ? AND obs_date >= ?
               ORDER BY obs_date""",
            (code, start),
        )
        result[code] = {
            "meta": dict(meta) if meta else {"code": code, "name_ko": code, "unit": ""},
            "points": [[r["obs_date"], r["value"]] for r in rows],
        }
    return {"range": range_key, "start": start, "series": result}


def curve() -> dict:
    """미 국채 수익률곡선: 최신 / 1개월 전 / 1년 전 비교."""
    codes = [curve_code(c) for c in CURVE_COLUMNS]
    latest_row = query_one(
        "SELECT MAX(obs_date) AS d FROM observations WHERE indicator_code = ?",
        (codes[CURVE_COLUMNS.index("10 Yr")],),
    )
    if not latest_row or not latest_row["d"]:
        return {"tenors": CURVE_TENORS, "labels": CURVE_COLUMNS, "lines": []}

    latest = date.fromisoformat(latest_row["d"])
    targets = [("최신", latest),
               ("1개월 전", latest - timedelta(days=30)),
               ("1년 전", latest - timedelta(days=365))]

    lines = []
    for label, target in targets:
        values, used = [], None
        for code in codes:
            row = query_one(
                """SELECT obs_date, value FROM observations
                   WHERE indicator_code = ? AND obs_date <= ?
                   ORDER BY obs_date DESC LIMIT 1""",
                (code, target.isoformat()),
            )
            values.append(row["value"] if row else None)
            if row and used is None:
                used = row["obs_date"]
        if any(v is not None for v in values):
            lines.append({"label": label, "date": used, "values": values})
    return {"tenors": CURVE_TENORS, "labels": CURVE_COLUMNS, "lines": lines}


def status() -> list[dict]:
    """수집기별 최근 실행 결과."""
    rows = query(
        """
        SELECT r.* FROM collection_runs r
        JOIN (SELECT collector, MAX(id) AS mid FROM collection_runs GROUP BY collector) m
          ON r.id = m.mid
        ORDER BY r.collector
        """
    )
    return [dict(r) for r in rows]
