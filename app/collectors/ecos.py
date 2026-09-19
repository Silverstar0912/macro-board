"""한국은행 ECOS 수집기.

source_id 형식: "STAT_CODE/CYCLE/ITEM_CODE1" (예: 722Y001/M/0101000)
ECOS_API_KEY 미설정 시 skipped 를 반환한다.
"""
from __future__ import annotations

from datetime import date

from ..config import ECOS_API_KEY
from ..db import upsert_observations
from ..registry import indicators_for
from .base import Result, http_get

BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
PAGE = 10000


def _period_range(cycle: str, start_year: int) -> tuple[str, str]:
    today = date.today()
    if cycle == "D":
        return f"{start_year}0101", today.strftime("%Y%m%d")
    if cycle == "M":
        return f"{start_year}01", today.strftime("%Y%m")
    if cycle == "Q":
        return f"{start_year}Q1", f"{today.year}Q4"
    return str(start_year), str(today.year)


def _to_iso(time_str: str, cycle: str) -> str:
    t = time_str.strip()
    if cycle == "D" and len(t) == 8:
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    if cycle == "M" and len(t) == 6:
        return f"{t[:4]}-{t[4:6]}-01"
    if cycle == "Q" and len(t) == 6:      # 2024Q1
        q = int(t[5])
        return f"{t[:4]}-{(q - 1) * 3 + 1:02d}-01"
    if len(t) == 4:
        return f"{t}-01-01"
    return t


def _fetch(stat: str, cycle: str, item: str, start_year: int) -> list[tuple[str, float]]:
    p_start, p_end = _period_range(cycle, start_year)
    out: list[tuple[str, float]] = []
    offset = 1
    while True:
        url = "/".join([BASE, ECOS_API_KEY, "json", "kr", str(offset),
                        str(offset + PAGE - 1), stat, cycle, p_start, p_end, item])
        payload = http_get(url).json()
        if "RESULT" in payload:                     # ECOS 는 오류도 200 으로 준다
            code = payload["RESULT"].get("CODE", "")
            if code == "INFO-200":                  # 데이터 없음 = 정상 종료
                break
            raise RuntimeError(f"ECOS {code}: {payload['RESULT'].get('MESSAGE', '')}")
        rows = payload.get("StatisticSearch", {}).get("row", [])
        if not rows:
            break
        for row in rows:
            raw = (row.get("DATA_VALUE") or "").strip()
            if not raw:
                continue
            try:
                out.append((_to_iso(row["TIME"], cycle), float(raw)))
            except (ValueError, KeyError):
                continue
        if len(rows) < PAGE:
            break
        offset += PAGE
    return out


def _yoy(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    lookup = dict(points)
    out = []
    for d, v in points:
        y, m, day = d.split("-")
        base = lookup.get(f"{int(y) - 1:04d}-{m}-{day}")
        if base:
            out.append((d, (v / base - 1) * 100))
    return out


def collect(start_year: int = 2015) -> Result:
    if not ECOS_API_KEY:
        return Result("ecos", "skipped", 0, "ECOS_API_KEY 미설정 — .env 에 키를 넣으면 활성화됩니다")

    total = 0
    failed: list[str] = []
    for ind in indicators_for("ecos"):
        try:
            stat, cycle, item = ind["source_id"].split("/")
            points = _fetch(stat, cycle, item, start_year)
        except Exception as exc:  # noqa: BLE001 - 지표 단위 격리
            failed.append(f"{ind['code']}({exc})"[:80])
            continue
        if ind["transform"] == "yoy":
            points = _yoy(points)
        total += upsert_observations(ind["code"], points)

    if total == 0 and failed:
        return Result("ecos", "error", 0, "전량 실패: " + " | ".join(failed))
    return Result("ecos", "ok", total, " | ".join(failed))


def backfill() -> Result:
    return collect(start_year=2000)
