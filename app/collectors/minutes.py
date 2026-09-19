"""FOMC 회의록·성명 수집기 (API 키 불필요).

연준 FOMC 캘린더 페이지에는 회의별로 성명(Statement)과 회의록(Minutes) 링크가 붙는다.
회의록은 회의 3주 뒤에 올라오므로, 캘린더를 주기적으로 훑으면 새 회의록이
공개되는 즉시 잡힌다.

원문 수집과 한글 요약은 분리돼 있다. 키가 없어도 원문은 계속 쌓이고,
나중에 키를 넣으면 밀린 문서까지 소급해서 요약한다.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..db import upsert_document
from ..services import translate as tr
from .base import Result, http_get

FOMC_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BASE = "https://www.federalreserve.gov"

MINUTES_RE = re.compile(r"/monetarypolicy/(fomcminutes(\d{4})(\d{2})(\d{2})\.htm)")
STATEMENT_RE = re.compile(r"/newsevents/pressreleases/(monetary(\d{4})(\d{2})(\d{2})a\.htm)")

# 최근 것만 본다 — 과거 회의록까지 전부 받아 요약하면 비용만 커진다
RECENT_LIMIT = 6


def _body(url: str) -> str:
    soup = BeautifulSoup(http_get(url, retries=2).text, "lxml")
    node = soup.select_one("#article, div.col-xs-12.col-sm-8.col-md-8") or soup.body
    if not node:
        return ""
    # 각주·내비게이션은 요약에 방해가 되므로 걷어낸다
    for junk in node.select("nav, script, style, .feedback"):
        junk.decompose()
    return node.get_text(" ", strip=True)


def _collect_type(page: str, pattern: re.Pattern, doc_type: str,
                  prefix: str, title_fmt: str) -> int:
    found = []
    seen = set()
    for match in pattern.finditer(page):
        path, year, month, day = match.groups()
        if path in seen:
            continue
        seen.add(path)
        found.append((f"{year}-{month}-{day}", prefix + path))

    found.sort(reverse=True)
    count = 0
    for meeting_date, url in found[:RECENT_LIMIT]:
        uid = f"{doc_type}:{meeting_date}"
        # 이미 본문까지 받아둔 문서는 다시 내려받지 않는다
        from ..db import query_one
        existing = query_one(
            "SELECT length(body) AS n FROM documents WHERE uid = ?", (uid,))
        if existing and (existing["n"] or 0) > 500:
            continue
        try:
            text = _body(url)
        except Exception:  # noqa: BLE001 - 문서 단위 격리
            continue
        if len(text) < 500:
            continue
        upsert_document(dict(
            uid=uid, doc_type=doc_type, meeting_date=meeting_date,
            published_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            title=title_fmt.format(date=meeting_date), url=url, body=text,
        ))
        count += 1
    return count


def collect() -> Result:
    notes: list[str] = []
    total = 0
    try:
        page = http_get(FOMC_CALENDAR).text
    except Exception as exc:  # noqa: BLE001
        return Result("minutes", "error", 0, f"캘린더 조회 실패: {exc}")

    try:
        total += _collect_type(page, MINUTES_RE, "minutes",
                               BASE + "/monetarypolicy/",
                               "FOMC 회의록 ({date})")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"minutes({type(exc).__name__})")

    try:
        total += _collect_type(page, STATEMENT_RE, "statement",
                               BASE + "/newsevents/pressreleases/",
                               "FOMC 성명 ({date})")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"statement({type(exc).__name__})")

    # 새로 받은 문서를 한글로 요약한다 (키가 없으면 조용히 건너뛴다)
    done, failed = tr.translate_pending(limit=3)
    if done:
        notes.append(f"한글 요약 {done}건")
    notes.extend(failed)

    status = "ok" if (total or done) else ("skipped" if not notes else "ok")
    return Result("minutes", status, total, "; ".join(notes))


def backfill() -> Result:
    return collect()
