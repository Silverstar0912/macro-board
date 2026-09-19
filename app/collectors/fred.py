"""FRED(세인트루이스 연은) 수집기.

FRED_API_KEY 가 없으면 error 가 아니라 skipped 를 반환한다 —
키가 없어도 대시보드 자체는 국채금리·발언·캘린더로 동작해야 하기 때문이다.
"""
from __future__ import annotations

from ..config import FRED_API_KEY
from ..db import upsert_observations
from ..registry import indicators_for
from .base import Result, http_get

API = "https://api.stlouisfed.org/fred/series/observations"


def _fetch_series(series_id: str, start: str = "1990-01-01") -> list[tuple[str, float]]:
    resp = http_get(API, params={
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start,
    })
    out: list[tuple[str, float]] = []
    for obs in resp.json().get("observations", []):
        raw = obs.get("value")
        if raw in (None, "", "."):
            continue
        try:
            out.append((obs["date"], float(raw)))
        except (ValueError, KeyError):
            continue
    return out


def _yoy(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """월간 시계열의 전년동월대비 변화율(%). 12개월 전 값이 있어야 계산한다."""
    lookup = dict(points)
    out: list[tuple[str, float]] = []
    for d, v in points:
        y, m, day = d.split("-")
        prev = f"{int(y) - 1:04d}-{m}-{day}"
        base = lookup.get(prev)
        if base:
            out.append((d, (v / base - 1) * 100))
    return out


def _diff(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """전기 대비 차이. 비농업고용처럼 '증감'이 의미 있는 계열에 쓴다."""
    return [(points[i][0], points[i][1] - points[i - 1][1])
            for i in range(1, len(points))]


TRANSFORMS = {"yoy": _yoy, "diff": _diff}


def collect(start: str = "1990-01-01") -> Result:
    if not FRED_API_KEY:
        return Result("fred", "skipped", 0, "FRED_API_KEY 미설정 — .env 에 키를 넣으면 활성화됩니다")

    total = 0
    failed: list[str] = []
    for ind in indicators_for("fred"):
        try:
            points = _fetch_series(ind["source_id"], start)
        except Exception as exc:  # noqa: BLE001 - 시리즈 단위로 격리
            failed.append(f"{ind['code']}({type(exc).__name__})")
            continue
        fn = TRANSFORMS.get(ind["transform"])
        if fn:
            points = fn(points)
        total += upsert_observations(ind["code"], points)

    if total == 0 and failed:
        return Result("fred", "error", 0, "전량 실패: " + ", ".join(failed))
    msg = f"실패: {', '.join(failed)}" if failed else ""
    return Result("fred", "ok", total, msg)


def backfill() -> Result:
    return collect(start="1970-01-01")
