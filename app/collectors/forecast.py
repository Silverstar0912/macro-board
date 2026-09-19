"""전망치 수집기.

블룸버그·로이터 컨센서스는 유료 데이터라 쓸 수 없다. 대신 공개된 공식 전망을 쓴다.

  1) 클리블랜드 연은 인플레이션 나우캐스팅 — 다음 CPI/PCE 발표에 대한 예측.
     매 영업일 갱신되므로 "이번 달 CPI 예상치" 로 바로 쓸 수 있다.
  2) FOMC 경제전망요약(SEP) 중간값 — 연준이 분기마다 내는 연도별 전망.
     정책금리·근원 PCE·실업률·성장률.

출처가 서로 다르니 화면에도 출처를 항상 함께 표시한다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from bs4 import BeautifulSoup

from ..config import FRED_API_KEY
from ..db import upsert_forecast
from .base import Result, http_get

CLEVELAND_URL = "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting"
FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"

# 나우캐스팅 표의 열 순서 → 우리 지표 코드 (전년비 표 기준)
NOWCAST_COLUMNS = ["US_CPI", "US_CORECPI", "US_PCE", "US_COREPCE"]

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

# FRED SEP 시리즈 → (지표 코드, 표기)
SEP_SERIES = {
    "FEDTARMD": ("US_POLICY", "FOMC 정책금리 전망(중간값)"),
    "JCXFECTM": ("US_COREPCE", "FOMC 근원 PCE 전망(중간값)"),
    "PCECTPICTM": ("US_PCE", "FOMC PCE 전망(중간값)"),
    "UNRATECTM": ("US_UNRATE", "FOMC 실업률 전망(중간값)"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_month(label: str) -> str | None:
    """'September 2026' → '2026-09-01'"""
    parts = label.strip().split()
    if len(parts) != 2 or parts[0] not in MONTHS:
        return None
    try:
        return f"{int(parts[1]):04d}-{MONTHS[parts[0]]:02d}-01"
    except ValueError:
        return None


def _collect_cleveland() -> int:
    """전년비 나우캐스팅 표를 읽는다.

    페이지에는 전월비 표와 전년비 표가 함께 있다. 우리 지표가 전년비라
    표 앞의 제목으로 전년비 표를 골라낸다 (표 순서에 의존하지 않는다).
    """
    soup = BeautifulSoup(http_get(CLEVELAND_URL).text, "lxml")

    # 페이지에는 월별 전월비 / 월별 전년비 / 분기 표가 함께 있고,
    # 설명 라벨은 각 표 '아래' 에 붙는다. 그래서 앞이 아니라 뒤를 본다.
    target = None
    for table in soup.select("table"):
        header = table.find(["th", "td"])
        if not header or header.get_text(strip=True).lower() != "month":
            continue                       # 분기 표는 건너뛴다
        label = table.find_next(["p", "h2", "h3", "h4", "caption"])
        text = label.get_text(" ", strip=True).lower() if label else ""
        if "year-over-year" in text:
            target = table
            break
    if target is None:
        raise RuntimeError("월별 전년비 나우캐스팅 표를 찾지 못했습니다")

    count = 0
    for tr in target.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if len(cells) < 5:
            continue
        period = _parse_month(cells[0])
        if not period:
            continue                       # 헤더행·주석행
        as_of = cells[5] if len(cells) > 5 else ""
        for code, raw in zip(NOWCAST_COLUMNS, cells[1:5]):
            if not re.fullmatch(r"-?\d+(\.\d+)?", raw or ""):
                continue                   # 아직 값이 없는 칸은 비어 있다
            upsert_forecast(dict(
                indicator_code=code, target_period=period, horizon="month",
                value=float(raw), source="클리블랜드 연은 나우캐스팅",
                as_of=as_of or _now()[:10], note="전년동월비",
            ))
            count += 1
    return count


def _collect_sep() -> int:
    """FOMC 경제전망요약(SEP) 중간값. FRED 키가 없으면 건너뛴다."""
    if not FRED_API_KEY:
        return 0
    count = 0
    this_year = date.today().year
    for series_id, (code, note) in SEP_SERIES.items():
        resp = http_get(FRED_OBS, params={
            "series_id": series_id, "api_key": FRED_API_KEY,
            "file_type": "json", "observation_start": f"{this_year}-01-01",
        })
        for obs in resp.json().get("observations", []):
            raw = obs.get("value")
            if raw in (None, "", "."):
                continue
            upsert_forecast(dict(
                indicator_code=code, target_period=obs["date"], horizon="year",
                value=float(raw), source="FOMC 경제전망(SEP)",
                as_of=obs.get("realtime_start"), note=note,
            ))
            count += 1
    return count


def collect() -> Result:
    total = 0
    failed: list[str] = []
    for name, fn in [("cleveland", _collect_cleveland), ("fomc-sep", _collect_sep)]:
        try:
            total += fn()
        except Exception as exc:  # noqa: BLE001 - 소스 단위 격리
            failed.append(f"{name}({type(exc).__name__})")

    if not FRED_API_KEY:
        failed.append("FRED_API_KEY 미설정 — FOMC 전망 비활성")
    if total == 0:
        return Result("forecast", "error", 0, "; ".join(failed) or "수집 결과 없음")
    return Result("forecast", "ok", total, "; ".join(failed))


def backfill() -> Result:
    return collect()
