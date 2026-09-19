"""지표 발표 감시 — 새 수치가 올라오면 즉시 알린다.

아침 브리핑만으로는 밤에 나온 지표를 다음 날에야 본다. CPI·PPI·고용처럼
장을 움직이는 지표는 발표 직후에 알아야 의미가 있다.

동작: 감시 대상 지표의 최근 관측치만 가볍게 받아 와서, 저장된 마지막 기간보다
새로운 기간이 생기면 텔레그램으로 알린다. 전 이력을 받는 fred 수집기와 달리
최근 몇 달만 보므로 30분마다 돌려도 부담이 없다.

첫 실행에서는 기준선만 기록하고 알리지 않는다 — 이미 나와 있던 값이
새 발표인 것처럼 무더기로 날아가면 안 되기 때문이다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..config import ENABLE_ALERTS
from ..db import query_one, tx, upsert_observations
from ..registry import BY_CODE
from .base import Result

log = logging.getLogger("releases")
KST = ZoneInfo("Asia/Seoul")

# 발표 즉시 알릴 지표 (코드, 알림 제목)
WATCHED: list[tuple[str, str]] = [
    ("US_CPI", "미국 소비자물가(CPI)"),
    ("US_CORECPI", "미국 근원 CPI"),
    ("US_PPI", "미국 생산자물가(PPI)"),
    ("US_COREPPI", "미국 근원 PPI"),
    ("US_COREPCE", "미국 근원 PCE"),
    ("US_UNRATE", "미국 실업률"),
    ("US_PAYEMS", "미국 비농업고용"),
    ("US_POLICY", "미국 기준금리(EFFR)"),
    ("KR_CPI", "한국 소비자물가"),
    ("KR_POLICY", "한국 기준금리"),
]

# 정책금리는 일별 계열이라 매일 값이 바뀐다. 발표로 볼 만한 변화만 알린다.
DAILY_CODES = {"US_POLICY"}
DAILY_MIN_CHANGE = 0.10   # %p


def _ensure_table() -> None:
    with tx() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS release_state (
                indicator_code TEXT PRIMARY KEY,
                last_period    TEXT NOT NULL,
                last_value     REAL,
                notified_at    TEXT
            )""")


def _recent_points(code: str) -> list[tuple[str, float]]:
    """감시 대상의 최근 관측치만 받아 온다."""
    ind = BY_CODE.get(code)
    if not ind:
        return []
    # 전년비는 12개월 전 값이 기준으로 필요하다. 창이 딱 1년이면 가장 최근 달의
    # 기준값이 창 밖으로 밀려 계산이 통째로 비므로 2년 이상 잡는다.
    start = (date.today() - timedelta(days=800)).isoformat()

    if ind["source"] == "fred":
        from .fred import TRANSFORMS, _fetch_series
        points = _fetch_series(ind["source_id"], start)
        fn = TRANSFORMS.get(ind["transform"])
        return fn(points) if fn else points

    if ind["source"] == "ecos":
        from .ecos import _fetch, _yoy
        stat, cycle, item = ind["source_id"].split("/")
        points = _fetch(stat, cycle, item, date.today().year - 2)
        return _yoy(points) if ind["transform"] == "yoy" else points

    return []


def _fmt(value: float, ind: dict) -> str:
    decimals = 2 if ind.get("decimals") is None else int(ind["decimals"])
    return f"{value:,.{decimals}f}{ind.get('unit') or ''}"


def _build_message(code: str, title: str, period: str,
                   value: float, prev: float | None) -> str:
    from ..services import forecasts as fc_svc

    ind = BY_CODE[code]
    lines = [f"🔔 <b>{title} 발표</b>"]

    period_label = period[:7].replace("-", ".")
    body = f"· {period_label}  <b>{_fmt(value, ind)}</b>"
    if prev is not None:
        diff = value - prev
        arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
        body += f"  <i>({arrow} 이전 {_fmt(prev, ind)})</i>"
    lines.append(body)

    # 예상치가 있었으면 상회/하회를 함께 보여준다 — 시장 반응의 핵심이다
    fc = query_one(
        """SELECT value, source FROM forecasts
           WHERE indicator_code = ? AND horizon = 'month' AND target_period = ?""",
        (code, period))
    if fc:
        gap = value - fc["value"]
        verdict = "상회" if gap > 0.005 else ("하회" if gap < -0.005 else "부합")
        lines.append(f"· 예상 {_fmt(fc['value'], ind)} → <b>{verdict}</b> "
                     f"<i>({gap:+.2f})</i>")
        lines.append(f"<i>예상치 출처: {fc['source']}</i>")

    lines.append(datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"))
    return "\n".join(lines)


def collect(notify: bool = True) -> Result:
    """감시 대상을 점검하고 새 발표를 알린다."""
    _ensure_table()
    from ..notify import telegram

    checked = 0
    alerts: list[str] = []
    failed: list[str] = []

    for code, title in WATCHED:
        try:
            points = _recent_points(code)
        except Exception as exc:  # noqa: BLE001 - 지표 단위로 격리
            failed.append(f"{code}({type(exc).__name__})")
            continue
        if not points:
            continue

        upsert_observations(code, points)
        checked += 1

        points.sort()
        period, value = points[-1]
        prev = points[-2][1] if len(points) > 1 else None

        state = query_one(
            "SELECT last_period, last_value FROM release_state WHERE indicator_code = ?",
            (code,))

        is_new = state is not None and period > state["last_period"]
        if is_new and code in DAILY_CODES:
            # 일별 정책금리는 매일 값이 바뀌므로 의미 있는 변동만 발표로 본다
            base = state["last_value"]
            is_new = base is not None and abs(value - base) >= DAILY_MIN_CHANGE

        # ENABLE_ALERTS 가 꺼진 쪽(클라우드 전환 후의 로컬 서버)은 기준선만
        # 따라가고 알리지 않는다. 안 그러면 같은 발표가 두 번 온다.
        if is_new and notify and ENABLE_ALERTS and telegram.configured():
            try:
                telegram.send(_build_message(code, title, period, value, prev))
                alerts.append(title)
                log.info("발표 알림: %s %s %s", title, period, value)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{code} 발송({type(exc).__name__})")

        with tx() as conn:
            conn.execute(
                """INSERT INTO release_state (indicator_code, last_period,
                                              last_value, notified_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(indicator_code) DO UPDATE SET
                       last_period=excluded.last_period,
                       last_value=excluded.last_value,
                       notified_at=excluded.notified_at""",
                (code, period, value,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))

    message = ("알림 " + ", ".join(alerts)) if alerts else f"{checked}개 점검"
    if failed:
        message += " | 실패: " + ", ".join(failed)
    status = "error" if (failed and not checked) else "ok"
    return Result("releases", status, len(alerts), message)


def backfill() -> Result:
    """기준선만 세우고 알리지 않는다."""
    return collect(notify=False)
