"""경제지표 발표일정 수집기.

  1) FOMC 회의 일정  : 연준 fomccalendars.htm 파싱 (키 불필요)
  2) 금통위 회의 일정 : 한국은행 통화정책방향 결정회의 페이지 파싱 (키 불필요)
  3) 미국 지표 발표일 : FRED releases/dates API (키 필요, 공식 발표일)
  4) 사용자 시드      : data/seed_events.json (그 밖에 직접 관리하는 일정)

BLS 사이트는 봇을 403 으로 차단하므로 발표일은 FRED 릴리스 캘린더로 대신한다.
일정을 임의로 추정해서 만들어 넣지는 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from ..config import DATA_DIR, FRED_API_KEY
from ..db import upsert_event
from .base import Result, http_get

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BOK_URL = "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do"
FRED_RELEASE_DATES = "https://api.stlouisfed.org/fred/releases/dates"
SEED_FILE = DATA_DIR / "seed_events.json"

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

# FRED 릴리스 이름 → (한글 표기, 중요도 1~3, 연결 지표)
WATCHED_RELEASES = {
    "Consumer Price Index": ("미국 소비자물가(CPI)", 3, "US_CPI"),
    "Employment Situation": ("미국 고용보고서", 3, "US_UNRATE"),
    "Personal Income and Outlays": ("미국 개인소득·지출(PCE)", 3, "US_COREPCE"),
    "Gross Domestic Product": ("미국 GDP", 3, None),
    "Producer Price Indexes": ("미국 생산자물가(PPI)", 3, "US_PPI"),
    "Advance Monthly Sales for Retail and Food Services": ("미국 소매판매", 2, None),
    "Job Openings and Labor Turnover Survey": ("미국 JOLTS 구인건수", 2, None),
    "University of Michigan: Consumer Sentiment": ("미시간대 소비자심리", 1, None),
}
# H.15(금리 통계)처럼 매 영업일 나오는 정기 릴리스는 넣지 않는다 —
# 캘린더가 매일 채워져 정작 봐야 할 지표 발표가 묻힌다.


def _uid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:20]


# ------------------------------------------------------------------ FOMC

def _collect_fomc() -> int:
    soup = BeautifulSoup(http_get(FOMC_URL).text, "lxml")
    count = 0
    for panel in soup.select("div.panel"):
        heading = panel.select_one(".panel-heading")
        if not heading:
            continue
        year_match = re.search(r"(20\d{2})", heading.get_text(" ", strip=True))
        if not year_match:
            continue
        year = int(year_match.group(1))
        for meeting in panel.select("div.fomc-meeting"):
            month_el = meeting.select_one(".fomc-meeting__month")
            date_el = meeting.select_one(".fomc-meeting__date")
            if not month_el or not date_el:
                continue
            month_name = month_el.get_text(" ", strip=True).split("/")[0].strip()
            month = MONTHS.get(month_name)
            if not month:
                continue
            # "27-28", "17-18*", "9-10 (unscheduled)" → 마지막 날(성명 발표일)을 잡는다
            days = re.findall(r"\d{1,2}", date_el.get_text(" ", strip=True))
            if not days:
                continue
            day = int(days[-1])
            try:
                event_date = date(year, month, day).isoformat()
            except ValueError:
                continue
            upsert_event(dict(
                uid=_uid("fomc", event_date),
                event_date=event_date, event_time="14:00 ET", country="US",
                title="FOMC 회의 결과 발표", importance=3,
                indicator_code="US_POLICY", actual=None, forecast=None,
                previous=None, source="Federal Reserve", url=FOMC_URL,
            ))
            count += 1
    return count


# ---------------------------------------------------------------- 금통위

_BOK_DATE_RE = re.compile(r"(\d{1,2})월\s*(\d{1,2})일")


def _collect_bok(years: int = 2) -> int:
    """한국은행 통화정책방향 결정회의(금통위) 일정.

    페이지는 연도별로 회의일자를 표로 제공한다. 아직 공표되지 않은 연도는
    표가 비어 있으므로 그냥 0건이 되고, 공표되면 다음 수집부터 자동으로 잡힌다.
    """
    count = 0
    this_year = date.today().year
    for year in range(this_year, this_year + years):
        resp = http_get(BOK_URL, params={"mtgSe": "A", "menuNo": "200755",
                                         "pYear": str(year)})
        table = BeautifulSoup(resp.text, "lxml").select_one("table")
        if not table:
            continue
        for tr in table.select("tr"):
            cell = tr.find(["th", "td"])
            if not cell:
                continue
            match = _BOK_DATE_RE.search(cell.get_text(" ", strip=True))
            if not match:
                continue                      # 헤더행("회의일자") 등
            month, day = int(match.group(1)), int(match.group(2))
            try:
                event_date = date(year, month, day).isoformat()
            except ValueError:
                continue
            upsert_event(dict(
                uid=_uid("bok", event_date),
                event_date=event_date, event_time="09:00 KST", country="KR",
                title="금통위 통화정책방향 결정", importance=3,
                indicator_code="KR_POLICY", actual=None, forecast=None,
                previous=None, source="한국은행",
                url=BOK_URL + "?mtgSe=A&menuNo=200755",
            ))
            count += 1
    return count


# ------------------------------------------------------------- FRED 릴리스

def _collect_fred_releases(days_ahead: int = 120, days_back: int = 30) -> int:
    if not FRED_API_KEY:
        return 0
    today = date.today()
    resp = http_get(FRED_RELEASE_DATES, params={
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "realtime_start": (today - timedelta(days=days_back)).isoformat(),
        "realtime_end": (today + timedelta(days=days_ahead)).isoformat(),
        "include_release_dates_with_no_data": "true",
        "limit": "1000",
        "sort_order": "asc",
    })
    count = 0
    for item in resp.json().get("release_dates", []):
        name = item.get("release_name", "")
        meta = next((v for k, v in WATCHED_RELEASES.items() if name.startswith(k)), None)
        if not meta:
            continue
        title_ko, importance, code = meta
        event_date = item.get("date")
        if not event_date:
            continue
        upsert_event(dict(
            uid=_uid("fred", str(item.get("release_id")), event_date),
            event_date=event_date, event_time="08:30 ET", country="US",
            title=title_ko, importance=importance, indicator_code=code,
            actual=None, forecast=None, previous=None, source="FRED",
            url="https://fred.stlouisfed.org/releases",
        ))
        count += 1
    return count


# ------------------------------------------------------------------ 시드

def _collect_seed() -> int:
    """data/seed_events.json 에 직접 넣은 일정을 반영한다.

    형식: [{"date":"2026-10-16","time":"09:00 KST","country":"KR",
            "title":"금통위 통화정책방향 결정","importance":3,
            "indicator_code":"KR_POLICY"}, ...]
    자동 수집이 어려운 한국 금통위 일정 등을 여기에 넣어 관리한다.
    """
    if not SEED_FILE.exists():
        return 0
    items = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    count = 0
    for it in items:
        if not it.get("date") or not it.get("title"):
            continue
        upsert_event(dict(
            uid=_uid("seed", it["date"], it["title"]),
            event_date=it["date"], event_time=it.get("time"),
            country=it.get("country", "KR"), title=it["title"],
            importance=int(it.get("importance", 2)),
            indicator_code=it.get("indicator_code"),
            actual=it.get("actual"), forecast=it.get("forecast"),
            previous=it.get("previous"), source="seed", url=it.get("url"),
        ))
        count += 1
    return count


def collect() -> Result:
    total = 0
    notes: list[str] = []
    for name, fn in [("fomc", _collect_fomc),
                     ("bok", _collect_bok),
                     ("fred-releases", _collect_fred_releases),
                     ("seed", _collect_seed)]:
        try:
            total += fn()
        except Exception as exc:  # noqa: BLE001 - 소스 단위 격리
            notes.append(f"{name}({type(exc).__name__})")

    if not FRED_API_KEY:
        notes.append("FRED_API_KEY 미설정 — 미국 지표 발표일 비활성")
    if total == 0:
        return Result("calendar", "error", 0, "; ".join(notes) or "수집 결과 없음")
    return Result("calendar", "ok", total, "; ".join(notes))


def backfill() -> Result:
    return collect()
