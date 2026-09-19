"""인프로세스 스케줄러.

APScheduler 없이 데몬 스레드 하나로 돌린다 — 수집기 수가 적고 주기가 분 단위라
별도 의존성을 추가할 이유가 없다. 각 수집기는 자기 주기를 독립적으로 갖는다.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .collectors import ORDER, run_one
from .config import BRIEF_TIME, ENABLE_TELEGRAM, SCHEDULE_SECONDS

KST = ZoneInfo("Asia/Seoul")

log = logging.getLogger("scheduler")

_thread: threading.Thread | None = None
_stop = threading.Event()
_next_run: dict[str, float] = {}


def _interval(name: str) -> int:
    # derived 는 원계열이 갱신될 때마다 함께 돌면 되므로 짧게 잡는다
    return SCHEDULE_SECONDS.get(name, 60 * 60)


def _next_brief_epoch() -> float:
    """다음 브리핑 발송 시각(에포크 초). BRIEF_TIME 은 Asia/Seoul 기준."""
    try:
        hour, minute = (int(x) for x in BRIEF_TIME.split(":"))
    except ValueError:
        hour, minute = 7, 30
    now = datetime.now(KST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.timestamp()


# 클라우드 틱이 07:25 에 뜨면 그때 보낸다 (GitHub 예약 실행은 수 분씩 늦는다).
BRIEF_EARLY_MINUTES = 5
# 이 시간이 지나도록 못 보냈으면 그날은 건너뛴다 — 점심에 '아침 브리핑' 은 어색하다.
BRIEF_WINDOW_HOURS = 6


def brief_due(now: datetime | None = None) -> bool:
    """오늘 아침 브리핑을 지금 보내야 하는가.

    클라우드는 30분마다 틱이 한 번씩 뜰 뿐 '07:30 에 실행' 을 보장하지 않는다.
    틱이 밀리거나 대기 중에 취소될 수도 있다. 그래서 '브리핑 시각이 지났고
    오늘 아직 안 보냈으면 보낸다' 로 판단한다 — 어느 틱이든 먼저 오는 쪽이 보낸다.
    """
    from .db import query_one

    now = now or datetime.now(KST)
    try:
        hour, minute = (int(x) for x in BRIEF_TIME.split(":"))
    except ValueError:
        hour, minute = 7, 30
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    start = target - timedelta(minutes=BRIEF_EARLY_MINUTES)
    if not (start <= now < target + timedelta(hours=BRIEF_WINDOW_HOURS)):
        return False

    # collection_runs.started_at 은 UTC 로 저장된다. 오늘(KST) 0시를 UTC 로 바꿔 비교한다.
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = midnight.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds")
    sent = query_one(
        """SELECT 1 FROM collection_runs
           WHERE collector = 'brief' AND status IN ('ok', 'skipped')
             AND started_at >= ?""",
        (since,),
    )
    return sent is None


def skip_brief_if_late(now: datetime | None = None) -> bool:
    """새로 시작한 날(빈 DB) 이미 브리핑 시각이 한참 지났으면 그날은 건너뛴다.

    빈 DB 는 '오늘 아직 안 보냄' 으로 보인다. 클라우드로 옮긴 날이나 캐시가
    사라진 날 한낮에 새로 시작하면, 이미 나간 브리핑이 한 번 더 가게 된다.
    07:25 에 새로 시작한 경우처럼 제시간이면 정상적으로 보낸다.
    """
    from .collectors.base import Result, run_collector

    now = now or datetime.now(KST)
    try:
        hour, minute = (int(x) for x in BRIEF_TIME.split(":"))
    except ValueError:
        hour, minute = 7, 30
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now <= target + timedelta(minutes=30) or not brief_due(now):
        return False
    run_collector("brief", lambda: Result(
        "brief", "skipped", 0, "새로 시작한 날 — 브리핑 시각이 지나 오늘은 건너뜀"))
    return True


def _send_brief_only() -> None:
    """브리핑 발송. 결과를 collection_runs 에 남긴다.

    발송이 조용히 실패하면 사용자는 '알람이 안 왔다' 는 사실만 알 뿐
    원인을 알 수 없다. 성공·실패를 모두 기록해 상태 배지에서 확인한다.
    """
    from .collectors.base import Result, run_collector
    from .notify import telegram
    from .services import brief

    def job() -> Result:
        if not telegram.configured():
            return Result("brief", "skipped", 0, "텔레그램 미설정")
        results = telegram.send(brief.build())
        ok = [r for r in results if r["ok"]]
        bad = [f"{r['chat_id']}: {r.get('error', '')}"[:80]
               for r in results if not r["ok"]]
        status = "ok" if ok and not bad else ("error" if not ok else "ok")
        return Result("brief", status, len(ok), "; ".join(bad))

    run_collector("brief", job)


def _loop() -> None:
    # 공유 보드 발행은 클라우드(GitHub Actions)가 맡는다. 로컬 서버는 실시간
    # 대시보드와 수집만 한다 — 로컬에서 보드를 올리면 클라우드 배포와 충돌한다.
    now = time.time()
    for name in ORDER:
        _next_run[name] = now          # 기동 직후 1회 전부 수집
    if ENABLE_TELEGRAM:
        # 브리핑은 기동 즉시 보내지 않는다 — 다음 예정 시각부터
        _next_run["brief"] = _next_brief_epoch()

    while not _stop.is_set():
        now = time.time()
        for name in ORDER:
            if now >= _next_run.get(name, 0):
                try:
                    run_one(name)
                except Exception:  # noqa: BLE001 - 루프는 절대 죽지 않는다
                    log.exception("[%s] 스케줄 실행 중 예외", name)
                _next_run[name] = time.time() + _interval(name)

        if "brief" in _next_run and now >= _next_run["brief"]:
            try:
                _send_brief_only()
            except Exception:  # noqa: BLE001 - 발송 실패로 수집까지 멈추면 안 된다
                log.exception("아침 브리핑 발송 실패")
            _next_run["brief"] = _next_brief_epoch()

        _stop.wait(30)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="collector-scheduler", daemon=True)
    _thread.start()
    log.info("스케줄러 시작: %s", ", ".join(f"{k}={_interval(k)}s" for k in ORDER))
    if ENABLE_TELEGRAM:
        log.info("아침 브리핑 예정 시각: 매일 %s (Asia/Seoul)", BRIEF_TIME)


def stop() -> None:
    _stop.set()


def next_runs() -> dict[str, float]:
    """다음 실행까지 남은 초."""
    now = time.time()
    return {k: max(0, round(v - now)) for k, v in _next_run.items()}
