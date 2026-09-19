"""시장 가격 수집기 (API 키 불필요).

FRED 의 시장 시리즈는 통계 공표 일정을 따르기 때문에 며칠씩 밀린다.
실제로 유가·천연가스는 8일, 환율·달러지수는 5일까지 지연됐다.
"오늘 가격" 을 보려는 화면에서 지난주 종가를 보여주는 건 틀린 값이나 마찬가지다.

그래서 거래되는 자산(환율·지수·에너지·금속)은 시장 시세를 직접 받는다.
FRED·LBMA 값과 정의가 다르므로(선물 vs 현물 고시가) 한 계열에 섞지 않고,
이 소스로 지정된 지표는 전 구간을 여기서만 받는다.

source_id 는 Yahoo 심볼이다 (KRW=X, CL=F, GC=F, ^GSPC ...).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..db import upsert_observations
from ..registry import indicators_for
from .base import Result, http_get

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def _fetch(symbol: str, period: str) -> list[tuple[str, float]]:
    resp = http_get(CHART.format(symbol=symbol),
                    params={"range": period, "interval": "1d"}, timeout=45)
    result = resp.json()["chart"]["result"][0]
    stamps = result.get("timestamp") or []
    closes = result["indicators"]["quote"][0].get("close") or []

    # 일봉 타임스탬프는 거래소 현지 개장 시각이다. UTC 로 그냥 변환하면
    # 시장에 따라 날짜가 하루 어긋나므로 거래소 오프셋을 반영한다.
    offset = timedelta(seconds=int(result.get("meta", {}).get("gmtoffset") or 0))

    out: list[tuple[str, float]] = []
    for stamp, close in zip(stamps, closes):
        if close is None:
            continue
        day = (datetime.fromtimestamp(stamp, timezone.utc) + offset).date()
        out.append((day.isoformat(), float(close)))

    # 장중이면 마지막 봉이 미확정 값이다. 그래도 최신 시세를 보여주는 편이
    # 지난주 종가보다 정확하므로 그대로 쓰고, 다음 수집 때 확정값으로 덮인다.
    meta = result.get("meta", {})
    price, market_time = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if price is not None and market_time:
        day = (datetime.fromtimestamp(market_time, timezone.utc) + offset).date()
        out.append((day.isoformat(), float(price)))
    return out


def collect(period: str = "1mo") -> Result:
    total = 0
    failed: list[str] = []
    for ind in indicators_for("yahoo"):
        try:
            points = _fetch(ind["source_id"], period)
        except Exception as exc:  # noqa: BLE001 - 심볼 단위로 격리
            failed.append(f"{ind['code']}({type(exc).__name__})")
            continue
        total += upsert_observations(ind["code"], points)

    if total == 0 and failed:
        return Result("yahoo", "error", 0, "전량 실패: " + ", ".join(failed))
    return Result("yahoo", "ok", total, f"실패: {', '.join(failed)}" if failed else "")


def backfill() -> Result:
    return collect(period="10y")
