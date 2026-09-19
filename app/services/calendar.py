"""발표일정 서비스 — 조회, 실제치 자동 결합, iCal 내보내기."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..db import query, query_one
from . import forecasts as fc_svc


def events(start: str | None = None, end: str | None = None,
           country: str | None = None, min_importance: int = 1) -> list[dict]:
    start = start or (date.today() - timedelta(days=14)).isoformat()
    end = end or (date.today() + timedelta(days=90)).isoformat()

    sql = """SELECT * FROM events
             WHERE event_date BETWEEN ? AND ? AND importance >= ?"""
    params: list = [start, end, min_importance]
    if country:
        sql += " AND country = ?"
        params.append(country)
    sql += " ORDER BY event_date, event_time"

    today = date.today().isoformat()
    out = []
    for row in query(sql, params):
        item = dict(row)
        item["is_past"] = item["event_date"] < today
        item["is_today"] = item["event_date"] == today
        # 발표가 지난 이벤트는 연결 지표의 실제 관측치를 붙여준다
        if item["is_past"] and item.get("indicator_code") and not item.get("actual"):
            obs = query_one(
                """SELECT obs_date, value FROM observations
                   WHERE indicator_code = ? ORDER BY obs_date DESC LIMIT 1""",
                (item["indicator_code"],),
            )
            if obs:
                item["actual"] = f'{obs["value"]:.2f}'
                item["actual_date"] = obs["obs_date"]
        # 아직 발표 전이면 공개 전망치를 붙여준다
        if not item["is_past"] and item.get("indicator_code") and not item.get("forecast"):
            fc = fc_svc.next_for(item["indicator_code"])
            if fc:
                item["forecast"] = f'{fc["value"]:.2f}'
                item["forecast_source"] = fc["source"]
        out.append(item)
    return out


def upcoming(days: int = 7) -> list[dict]:
    today = date.today()
    return events(today.isoformat(), (today + timedelta(days=days)).isoformat())


def to_ics(items: list[dict]) -> str:
    """개인 캘린더 구독용 iCalendar 문서."""
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Macro Dashboard//KR", "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:거시경제지표 발표일정",
    ]
    for ev in items:
        day = ev["event_date"].replace("-", "")
        stars = "★" * int(ev.get("importance") or 1)
        summary = f"[{ev.get('country', '')}] {ev['title']} {stars}"
        desc_parts = [p for p in [ev.get("event_time"), ev.get("source")] if p]
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.get('uid') or ev['id']}@macro-dashboard",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{day}",
            f"DTEND;VALUE=DATE:{day}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(' / '.join(desc_parts))}",
        ]
        if ev.get("url"):
            lines.append(f"URL:{ev['url']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
