"""미 재무부 일별 국채 수익률곡선 수집기 (API 키 불필요).

연도별 CSV 를 받아 (날짜, 만기) 격자를 observations 로 적재한다.
백필 시에는 여러 연도를 순회하고, 평소에는 올해치만 갱신한다.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from ..db import upsert_observations
from ..registry import indicators_for
from .base import Result, http_get

BASE = ("https://home.treasury.gov/resource-center/data-chart-center/"
        "interest-rates/daily-treasury-rates.csv/{year}/all")

# 수익률곡선 만기 → 프론트 곡선 차트에서 쓰는 순서
CURVE_COLUMNS = ["1 Mo", "2 Mo", "3 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr",
                 "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr"]
CURVE_TENORS = [1 / 12, 2 / 12, 3 / 12, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]


def curve_code(column: str) -> str:
    """수익률곡선 만기 컬럼이 실제로 저장되는 지표 코드.

    카탈로그에 있는 만기(2 Yr → US2Y 등)는 그 코드로 저장되고,
    없는 만기만 UST_ 접두 코드로 따로 적재된다. 조회 쪽에서 같은 규칙을
    다시 쓰다 어긋나지 않도록 여기 한 곳에서만 결정한다.
    """
    for ind in indicators_for("treasury"):
        if ind["source_id"] == column:
            return ind["code"]
    return "UST_" + column.replace(" ", "")


def _fetch_year(year: int) -> list[dict]:
    url = BASE.format(year=year)
    resp = http_get(url, params={"type": "daily_treasury_yield_curve",
                                 "field_tdr_date_value": str(year),
                                 "_format": "csv"})
    text = resp.text.lstrip("﻿")
    return list(csv.DictReader(io.StringIO(text)))


def _to_iso(mmddyyyy: str) -> str:
    m, d, y = mmddyyyy.strip().split("/")
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def collect(years: int = 1) -> Result:
    """years=1 이면 올해만, 크게 주면 그만큼 과거로 백필한다."""
    wanted = {i["source_id"]: i["code"] for i in indicators_for("treasury")}
    # 수익률곡선 탭용으로 카탈로그에 없는 만기도 함께 적재한다
    for col in CURVE_COLUMNS:
        wanted.setdefault(col, curve_code(col))

    buckets: dict[str, list[tuple[str, float]]] = {c: [] for c in wanted.values()}
    this_year = date.today().year
    fetched_years = 0
    errors: list[str] = []

    for year in range(this_year, this_year - years, -1):
        try:
            rows = _fetch_year(year)
        except Exception as exc:  # noqa: BLE001 - 특정 연도 실패는 건너뛴다
            errors.append(f"{year}:{type(exc).__name__}")
            continue
        fetched_years += 1
        for row in rows:
            raw_date = row.get("Date")
            if not raw_date:
                continue
            iso = _to_iso(raw_date)
            for col, code in wanted.items():
                raw = (row.get(col) or "").strip()
                if not raw:
                    continue
                try:
                    buckets[code].append((iso, float(raw)))
                except ValueError:
                    continue

    total = sum(upsert_observations(code, pts) for code, pts in buckets.items() if pts)
    if total == 0:
        return Result("treasury", "error", 0, "수집된 데이터 없음 " + ",".join(errors))
    msg = f"{fetched_years}개 연도"
    if errors:
        msg += f" (실패: {','.join(errors)})"
    return Result("treasury", "ok", total, msg)


def backfill() -> Result:
    """최초 실행용 — 최근 15년치 이력 적재."""
    return collect(years=15)
