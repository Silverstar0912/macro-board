"""아침 브리핑 본문 생성.

대시보드에 있는 것과 같은 데이터를 텔레그램 메시지 한 장으로 압축한다.
숫자는 DB 에 있는 값만 쓰고, 없는 지표는 조용히 건너뛴다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import SNAPSHOT_URL
from . import calendar as cal_svc
from . import documents as doc_svc
from . import forecasts as fc_svc
from . import indicators as ind_svc

KST = ZoneInfo("Asia/Seoul")
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 브리핑에 넣을 지표를 섹션별로 정의한다 (코드, 표시명)
SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("정책금리", [("US_POLICY", "미국 EFFR"), ("KR_POLICY", "한국 기준금리")]),
    ("미 국채", [("US2Y", "2년"), ("US10Y", "10년"), ("US30Y", "30년"),
                 ("US10Y2Y", "10Y-2Y")]),
    ("미국 물가·고용", [("US_CPI", "CPI"), ("US_CORECPI", "근원 CPI"),
                        ("US_PPI", "PPI"), ("US_COREPCE", "근원 PCE"),
                        ("US_UNRATE", "실업률")]),
    ("한국", [("KR3Y", "국고채 3년"), ("KR10Y", "국고채 10년"),
              ("KR_CPI", "소비자물가"), ("USDKRW", "원/달러")]),
    ("시장", [("SPX", "S&P 500"), ("DXY", "달러지수")]),
    ("원자재", [("WTI", "WTI"), ("GOLD", "금"), ("SILVER", "은"),
                ("COPPER", "구리")]),
]

RATE_CATEGORIES = {"금리", "정책금리"}


def _fmt_change(item: dict) -> str:
    """금리는 bp, 나머지 % 지표는 %p, 그 외는 원단위 — 대시보드와 같은 규칙."""
    v = item.get("change")
    if v is None:
        return ""
    if v == 0:
        return "보합"
    unit = item.get("unit") or ""
    if unit in ("%", "%p"):
        if item.get("category") in RATE_CATEGORIES:
            return f"{v * 100:+.0f}bp"
        return f"{v:+.2f}%p"
    return f"{v:+,.2f}"


def _fmt_value(item: dict) -> str:
    decimals = item.get("decimals")
    decimals = 2 if decimals is None else int(decimals)
    return f"{item['latest']:,.{decimals}f}{item.get('unit') or ''}"


def build(now: datetime | None = None) -> str:
    """텔레그램 HTML parse_mode 용 브리핑 본문."""
    now = now or datetime.now(KST)
    today = now.date()
    by_code = {i["code"]: i for i in ind_svc.summary()}

    head = (f"<b>📊 거시경제 브리핑</b>\n"
            f"{today.strftime('%Y년 %m월 %d일')} ({WEEKDAY_KO[today.weekday()]})\n")
    lines = [head]

    for title, members in SECTIONS:
        rows = []
        for code, label in members:
            item = by_code.get(code)
            if not item or not item.get("has_data"):
                continue
            change = _fmt_change(item)
            suffix = f"  <i>{change}</i>" if change else ""
            rows.append(f"· {label} <b>{_fmt_value(item)}</b>{suffix}")
        if rows:
            lines.append(f"<b>【{title}】</b>\n" + "\n".join(rows))

    forecast = _forecast_block()
    if forecast:
        lines.append(forecast)
    lines.append(_calendar_block(today))

    minutes = _minutes_block(today)
    if minutes:
        lines.append(minutes)

    stale = _staleness_note(by_code)
    if stale:
        lines.append(stale)

    link = _link_block()
    if link:
        lines.append(link)

    return "\n\n".join(lines)


def _link_block() -> str:
    """브리핑에 붙일 바로가기.

    LAN 대시보드 주소는 넣지 않는다 — 받는 사람이 같은 공유기 밖에 있으면
    열리지 않는 링크라 오히려 혼란만 준다. 어디서나 열리는 스냅샷만 건다.
    """
    if not SNAPSHOT_URL:
        return ""
    return f'🌐 <a href="{SNAPSHOT_URL}">브리핑 보드 열기</a>'


# 예상치를 보여줄 지표 (코드, 표시명)
FORECAST_ITEMS = [("US_CPI", "CPI"), ("US_CORECPI", "근원 CPI"),
                  ("US_COREPCE", "근원 PCE")]


def _forecast_block() -> str:
    """다음 발표에 대한 공개 전망치.

    시장 컨센서스(블룸버그·로이터)는 유료라 쓸 수 없어 클리블랜드 연은
    나우캐스팅을 쓴다. 성격이 다른 숫자이므로 출처를 반드시 함께 적는다.
    """
    rows, sources = [], set()
    for code, label in FORECAST_ITEMS:
        fc = fc_svc.next_for(code)
        if not fc:
            continue
        period = fc["target_period"][:7].replace("-", ".")
        rows.append(f"· {label} <b>{fc['value']:.2f}%</b> <i>({period} 예상)</i>")
        sources.add(fc["source"])
    if not rows:
        return ""
    tail = f"\n<i>출처: {' · '.join(sorted(sources))}</i>"
    return "<b>【다음 발표 예상치】</b>\n" + "\n".join(rows) + tail


def _calendar_block(today: date) -> str:
    """오늘 ~ 향후 7일 발표일정."""
    events = cal_svc.events(today.isoformat(),
                            (today + timedelta(days=7)).isoformat(),
                            min_importance=2)
    if not events:
        return "<b>【발표일정】</b>\n· 향후 7일간 예정된 주요 발표가 없습니다."

    rows = []
    for ev in events:
        day = date.fromisoformat(ev["event_date"])
        mark = "🔴 오늘" if ev["event_date"] == today.isoformat() else \
               f"{day.month:02d}/{day.day:02d}({WEEKDAY_KO[day.weekday()]})"
        stars = "★" * int(ev.get("importance") or 1)
        time_part = f" {ev['event_time']}" if ev.get("event_time") else ""
        fc = f"  <i>예상 {ev['forecast']}</i>" if ev.get("forecast") else ""
        rows.append(f"· {mark}{time_part} {ev['title']} {stars}{fc}")
    return "<b>【발표일정 · 향후 7일】</b>\n" + "\n".join(rows)


TONE_KO = {"hawkish": "매파", "dovish": "비둘기파", "neutral": "중립"}
MINUTES_FRESH_DAYS = 10


def _minutes_block(today: date) -> str:
    """최근 공개된 FOMC 회의록 요약.

    회의록은 6~8주에 한 번 나오므로 매일 넣으면 금방 배경 소음이 된다.
    공개 직후 열흘만 브리핑에 띄우고, 그 뒤에는 보드에서 보게 한다.
    """
    doc = doc_svc.latest_minutes()
    if not doc or not doc.get("translated_at"):
        return ""
    try:
        published = date.fromisoformat(doc["translated_at"][:10])
    except (ValueError, TypeError):
        return ""
    if (today - published).days > MINUTES_FRESH_DAYS:
        return ""

    headline = (doc.get("summary_ko") or "").split("\n\n")[0].strip()
    tone = TONE_KO.get(doc.get("tone"), "")
    tone_part = f" <i>({tone})</i>" if tone else ""
    body = f"· {headline}" if headline else ""
    return (f"<b>【FOMC 회의록 · {doc['meeting_date']}】</b>{tone_part}\n{body}\n"
            f'<a href="{doc.get("url", "")}">원문</a>')


def _staleness_note(by_code: dict) -> str:
    """멈춘 지표를 알린다.

    수집이 조용히 막히면 지난주 값을 오늘 값으로 읽게 된다. 브리핑은 매일
    나가므로 여기서 잡아주는 게 가장 빠르다. 브리핑에 실리는 지표만 본다.
    """
    stale = []
    for _, members in SECTIONS:
        for code, label in members:
            item = by_code.get(code)
            if item and item.get("stale"):
                stale.append(f"{label} {item['lag_days']}일")
    if not stale:
        return ""
    return "⚠️ 갱신이 멈춘 지표: " + ", ".join(stale)


def build_plain() -> str:
    """터미널 미리보기용 — 태그를 걷어내고 링크는 주소만 남긴다."""
    import re
    text = build()
    text = re.sub(r'<a href="([^"]+)">([^<]*)</a>', r"\2 \1", text)
    return re.sub(r"</?(b|i)>", "", text)
