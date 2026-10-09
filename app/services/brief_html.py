"""아침 브리핑 — 텔레그램에 첨부하는 단일 HTML 파일.

브리핑 보드(snapshot.py)는 ECharts 와 스크립트로 화면을 그려서, 휴대폰 텔레그램의 문서 미리보기처럼
스크립트가 막힌 곳에서는 빈 페이지가 된다. 그래서 텔레그램 브리핑과 같은 데이터를 **서버에서 다 그려
넣은** 정적 HTML 을 따로 만든다 — 외부 파일·스크립트 없음, 1년 추이는 인라인 SVG 스파크라인.

    build() -> str
    write(path) -> Path
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from pathlib import Path

from . import brief
from . import calendar as cal_svc
from . import documents as doc_svc
from . import forecasts as fc_svc
from . import indicators as ind_svc

PROVIDER = "이마고 리서치 제공"
CAL_DAYS = 14

CSS = """
:root{--bg:#f4f5f7;--panel:#fff;--line:#dfe3e8;--soft:#eceff2;--text:#1c2024;--muted:#68717d;--faint:#9aa2ac;
--head:#eef1f4;--accent:#2b59c3;--up:#d23c3c;--down:#2360d8;--warn:#b7791f;--warn-soft:#fbf1de;--spark:#2b59c3}
@media (prefers-color-scheme:dark){:root{--bg:#101317;--panel:#161a1f;--line:#2a3038;--soft:#20252c;--text:#e4e7eb;
--muted:#9aa3ad;--faint:#6c7580;--head:#1c2127;--accent:#7ea2ff;--up:#ff6b6b;--down:#6fa4ff;--warn:#ddb35a;--warn-soft:#33290f;--spark:#7ea2ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 "Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;-webkit-text-size-adjust:100%}
.wrap{max-width:860px;margin:0 auto;padding:16px 16px 48px}
h1{font-size:20px;margin:4px 0 2px}
.sub{color:var(--muted);font-size:12.5px}
.provider{color:var(--muted);font-size:13px;margin-top:2px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;margin-top:14px}
.panel h2{font-size:14px;margin:0 0 8px}
.panel h2 small{color:var(--muted);font-weight:400;font-size:12px;margin-left:6px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13px}
th,td{padding:6px 8px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--soft)}
th{background:var(--head);color:var(--muted);font-weight:600;font-size:12px}
th:first-child,td:first-child{text-align:left}
td.spark{padding:2px 8px}
svg{display:block}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--muted)}
.stale{color:var(--warn);font-size:11px}
.warn{margin-top:14px;padding:9px 12px;border-radius:8px;background:var(--warn-soft);color:var(--warn);font-size:12.5px}
.minutes p{margin:6px 0;white-space:pre-line}
.tone{display:inline-block;padding:0 8px;border-radius:10px;background:var(--head);color:var(--muted);font-size:12px;margin-left:6px}
.ev{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px}
.ev .d{color:var(--muted);white-space:nowrap}
.ev .today{color:var(--up);font-weight:700}
.foot{margin-top:22px;color:var(--faint);font-size:12px}
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _change_html(item: dict) -> str:
    txt = brief._fmt_change(item)
    v = item.get("change")
    if not txt:
        return "—"
    cls = "flat" if v == 0 else ("up" if v > 0 else "down")
    return f'<span class="{cls}">{_e(txt)}</span>'


def _yoy_html(item: dict) -> str:
    v = item.get("yoy_change")
    if v is None:
        return "—"
    fake = dict(item, change=v)
    txt = brief._fmt_change(fake)
    cls = "flat" if v == 0 else ("up" if v > 0 else "down")
    return f'<span class="{cls}">{_e(txt)}</span>'


def _spark(points: list, w: int = 120, h: int = 28) -> str:
    """1년 추이 스파크라인 — 외부 라이브러리 없이 인라인 SVG."""
    vals = [p[1] for p in points if p[1] is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(vals)
    pts = " ".join(f"{i * (w - 2) / (n - 1) + 1:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}" for i, v in enumerate(vals))
    last_x = w - 1
    last_y = h - 2 - (vals[-1] - lo) / span * (h - 4)
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<polyline fill="none" stroke="var(--spark)" stroke-width="1.5" points="{pts}"/>'
            f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2" fill="var(--spark)"/></svg>')


def _sections(by_code: dict, series: dict) -> str:
    out = []
    for title, members in brief.SECTIONS:
        rows = ""
        for code, label in members:
            item = by_code.get(code)
            if not item or not item.get("has_data"):
                continue
            stale = (f'<div class="stale">⚠ {item.get("lag_days")}일 전 값</div>' if item.get("stale") else "")
            rows += (f"<tr><td>{_e(label)}{stale}</td><td><b>{_e(brief._fmt_value(item))}</b></td>"
                     f"<td>{_change_html(item)}</td><td>{_yoy_html(item)}</td>"
                     f"<td class='spark'>{_spark((series.get(code) or {}).get('points') or [])}</td>"
                     f"<td><small style='color:var(--faint)'>{_e((item.get('latest_date') or '')[5:])}</small></td></tr>")
        if rows:
            out.append(f'<div class="panel"><h2>{_e(title)}</h2><div class="scroll"><table>'
                       f"<tr><th>지표</th><th>값</th><th>직전 대비</th><th>1년 전 대비</th><th>1년 추이</th><th>기준일</th></tr>"
                       f"{rows}</table></div></div>")
    return "".join(out)


def _forecast() -> str:
    rows, sources = "", set()
    for code, label in brief.FORECAST_ITEMS:
        fc = fc_svc.next_for(code)
        if not fc:
            continue
        period = fc["target_period"][:7].replace("-", ".")
        rows += f"<tr><td>{_e(label)}</td><td><b>{fc['value']:.2f}%</b></td><td>{_e(period)} 발표분</td></tr>"
        sources.add(fc["source"])
    if not rows:
        return ""
    return (f'<div class="panel"><h2>다음 발표 예상치<small>출처: {_e(" · ".join(sorted(sources)))}</small></h2>'
            f"<table><tr><th>지표</th><th>예상</th><th>대상</th></tr>{rows}</table></div>")


def _calendar(today: date) -> str:
    events = cal_svc.events(today.isoformat(), (today + timedelta(days=CAL_DAYS)).isoformat(), min_importance=2)
    if not events:
        return (f'<div class="panel"><h2>발표일정<small>향후 {CAL_DAYS}일</small></h2>'
                f"<div class='sub'>예정된 주요 발표가 없습니다.</div></div>")
    rows = ""
    for ev in events:
        day = date.fromisoformat(ev["event_date"])
        is_today = ev["event_date"] == today.isoformat()
        mark = "오늘" if is_today else f"{day.month:02d}/{day.day:02d} ({brief.WEEKDAY_KO[day.weekday()]})"
        t = f" {ev['event_time']}" if ev.get("event_time") else ""
        stars = "★" * int(ev.get("importance") or 1)
        fc = f" <small style='color:var(--muted)'>예상 {_e(ev['forecast'])}</small>" if ev.get("forecast") else ""
        rows += f"<div class='d {'today' if is_today else ''}'>{mark}{t}</div><div>{_e(ev['title'])} <small>{stars}</small>{fc}</div>"
    return f'<div class="panel"><h2>발표일정<small>향후 {CAL_DAYS}일</small></h2><div class="ev">{rows}</div></div>'


def _minutes(today: date) -> str:
    doc = doc_svc.latest_minutes()
    if not doc or not doc.get("summary_ko"):
        return ""
    tone = brief.TONE_KO.get(doc.get("tone"), "")
    tone_html = f'<span class="tone">{_e(tone)}</span>' if tone else ""
    paras = "".join(f"<p>{_e(p.strip())}</p>" for p in (doc["summary_ko"] or "").split("\n\n") if p.strip())
    reason = f"<p class='sub'>{_e(doc['tone_reason'])}</p>" if doc.get("tone_reason") else ""
    link = f'<a href="{_e(doc.get("url") or "")}">원문</a>' if doc.get("url") else ""
    return (f'<div class="panel minutes"><h2>FOMC 회의록 · {_e(doc.get("meeting_date"))}{tone_html}'
            f"<small>{link}</small></h2>{paras}{reason}</div>")


def _stale_note(by_code: dict) -> str:
    txt = brief._staleness_note(by_code)
    return f'<div class="warn">{_e(txt)}</div>' if txt else ""


def build(now: datetime | None = None) -> str:
    now = now or datetime.now(brief.KST)
    today = now.date()
    by_code = {i["code"]: i for i in ind_svc.summary()}
    codes = [c for _, members in brief.SECTIONS for c, _ in members]
    series = ind_svc.series(codes, "1Y")["series"]
    title = f"거시경제 브리핑 {today.strftime('%Y년 %m월 %d일')} ({brief.WEEKDAY_KO[today.weekday()]})"
    parts = [f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)} · 이마고 리서치</title><style>{CSS}</style></head><body><div class="wrap">
<div class="sub">아침 브리핑</div>
<h1>📊 {_e(title)}</h1>
<div class="provider">{PROVIDER}</div>
<div class="sub">값은 각 지표의 최신 관측치 · 직전 관측 대비 · 금리는 bp, 물가·고용은 %p</div>""",
             _sections(by_code, series), _forecast(), _calendar(today), _minutes(today), _stale_note(by_code),
             f"""<div class="foot">출처: 한국은행 ECOS · 미 재무부 · 연준 · FRED · 클리블랜드 연은(예상치). 생성 {now:%Y-%m-%d %H:%M} KST</div>
</div></body></html>"""]
    return "\n".join(p for p in parts if p)


def write(path: str | Path, now: datetime | None = None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build(now), encoding="utf-8")
    return p
