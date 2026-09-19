"""수집기 레지스트리."""
from __future__ import annotations

from ..db import query, upsert_observations
from . import (calendar_src, ecos, forecast, fred, minutes, releases,
               speeches, treasury, yahoo)
from .base import Result, run_collector


def _collect_derived() -> Result:
    """파생 지표 계산. 현재는 미 10Y-2Y 스프레드."""
    rows = query(
        """
        SELECT a.obs_date AS d, a.value - b.value AS v
        FROM observations a
        JOIN observations b ON a.obs_date = b.obs_date
        WHERE a.indicator_code = 'US10Y' AND b.indicator_code = 'US2Y'
        """
    )
    n = upsert_observations("US10Y2Y", [(r["d"], r["v"]) for r in rows])
    return Result("derived", "ok", n, "")


COLLECTORS = {
    "treasury": treasury.collect,
    "fred": fred.collect,
    "ecos": ecos.collect,
    "yahoo": yahoo.collect,
    "speeches": speeches.collect,
    "calendar": calendar_src.collect,
    "forecast": forecast.collect,
    "releases": releases.collect,
    "minutes": minutes.collect,
    "derived": _collect_derived,
}

BACKFILLERS = {
    "treasury": treasury.backfill,
    "fred": fred.backfill,
    "ecos": ecos.backfill,
    "yahoo": yahoo.backfill,
    "speeches": speeches.backfill,
    "calendar": calendar_src.backfill,
    "forecast": forecast.backfill,
    "releases": releases.backfill,
    "minutes": minutes.backfill,
    "derived": _collect_derived,
}

# 파생 지표는 원계열 뒤에 계산돼야 한다
# releases 는 fred/ecos 뒤에 둔다 — 같은 값을 두 번 알리지 않도록
ORDER = ["treasury", "fred", "ecos", "yahoo", "derived", "speeches", "calendar",
         "forecast", "minutes", "releases"]


def run_one(name: str, *, backfill: bool = False) -> Result:
    table = BACKFILLERS if backfill else COLLECTORS
    if name not in table:
        return Result(name, "error", 0, f"알 수 없는 수집기: {name}")
    return run_collector(name, table[name])


def run_all(*, backfill: bool = False) -> list[Result]:
    return [run_one(name, backfill=backfill) for name in ORDER]


# 클라우드 cron 은 정시에 딱 맞춰 뜨지 않는다 (수 분씩 늦는다). 30분 주기 수집기가
# 29분 만에 불려도 건너뛰지 않도록 이만큼 여유를 둔다.
DUE_SLACK_SECONDS = 5 * 60


def run_due() -> list[Result]:
    """주기가 된 수집기만 돌린다.

    서버 안의 스케줄러는 메모리에 다음 실행 시각을 들고 있지만, 클라우드에서는
    매번 새 머신이 떠서 한 번 돌고 사라진다. 그래서 '마지막으로 성공한 시각' 을
    DB(collection_runs) 에서 읽어 수집기별 주기를 지킨다. 실패한 수집기는
    다음 틱에 다시 시도된다.
    """
    from datetime import datetime, timezone

    from ..config import SCHEDULE_SECONDS
    from ..db import query_one

    now = datetime.now(timezone.utc)
    results = []
    for name in ORDER:
        interval = SCHEDULE_SECONDS.get(name, 60 * 60)
        row = query_one(
            """SELECT MAX(started_at) AS t FROM collection_runs
               WHERE collector = ? AND status IN ('ok', 'skipped')""",
            (name,),
        )
        if row and row["t"]:
            elapsed = (now - datetime.fromisoformat(row["t"])).total_seconds()
            if elapsed < interval - DUE_SLACK_SECONDS:
                continue
        results.append(run_one(name))
    return results
