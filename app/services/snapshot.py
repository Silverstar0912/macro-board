"""공유용 스냅샷 HTML 생성.

로컬 대시보드는 LAN 안에서만 열린다. 그룹 채팅방처럼 밖에 있는 사람과
나누려면 서버가 필요 없는 한 장짜리 HTML 이어야 한다.
그래서 수치·시계열·일정·발언을 전부 페이지 안에 심어 자체 완결형으로 만든다.

    python run.py --snapshot            # data/snapshot.html 생성
    python run.py --snapshot 경로.html   # 경로 지정
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import calendar as cal_svc
from . import indicators as ind_svc
from . import documents as doc_svc
from . import forecasts as fc_svc
from . import speeches as sp_svc

KST = ZoneInfo("Asia/Seoul")
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 스냅샷에 넣을 시계열. 너무 많으면 페이지가 무거워지므로 골라 담는다.
CHART_SERIES = [
    "US_POLICY", "US2Y", "US10Y", "US30Y", "US10Y2Y",
    "KR_POLICY", "KR3Y", "KR10Y",
    "US_CPI", "US_CORECPI", "US_PPI", "US_COREPCE", "US_UNRATE", "KR_CPI",
    "USDKRW", "SPX",
    "WTI", "BRENT", "GOLD", "SILVER", "COPPER", "NGAS",
]
MAX_POINTS = 1400          # 계열당 최대 점 개수 (균등 샘플링)


def _downsample(points: list[list]) -> list[list]:
    """오래된 구간을 솎아낸다. 마지막 점은 반드시 남긴다 (최신값이 어긋나면 안 된다)."""
    if len(points) <= MAX_POINTS:
        return points
    step = len(points) / MAX_POINTS
    picked = [points[int(i * step)] for i in range(MAX_POINTS)]
    if picked[-1] != points[-1]:
        picked[-1] = points[-1]
    return picked


def build_data() -> dict:
    today = date.today()
    summary = ind_svc.summary()

    series = {}
    for code in CHART_SERIES:
        payload = ind_svc.series([code], "MAX")["series"].get(code)
        if not payload or not payload["points"]:
            continue
        series[code] = {
            "name": payload["meta"].get("name_ko", code),
            "unit": payload["meta"].get("unit", ""),
            "category": payload["meta"].get("category", ""),
            "points": _downsample(payload["points"]),
        }

    events = cal_svc.events((today - timedelta(days=30)).isoformat(),
                            (today + timedelta(days=180)).isoformat())

    return {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "today": today.isoformat(),
        "indicators": [i for i in summary if i.get("has_data")],
        "series": series,
        "curve": ind_svc.curve(),
        "forecast_yearly": fc_svc.yearly_table(),
        "documents": doc_svc.feed(8, translated_only=True),
        "events": events,
        "speeches": sp_svc.feed(18),
        "tone_stats": sp_svc.tone_stats(30),
    }


def build_html() -> str:
    data = json.dumps(build_data(), ensure_ascii=False, separators=(",", ":"))
    return (_HEAD
            + _BODY
            + '\n<script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js"></script>\n'
            + '<script>\nconst DATA = ' + data + ';\n' + _SCRIPT + '\n</script>\n')


def _check(html: str) -> None:
    """생성물 자체 검사.

    이 페이지의 JS 는 파이썬 문자열 안에 들어 있어서, 이스케이프가 한 겹
    벗겨지면 문자열 리터럴 안에 실제 줄바꿈이 들어가고 스크립트 전체가
    파싱에 실패한다. 그러면 정적 HTML 만 남아 '빈 페이지' 처럼 보이는데,
    브라우저를 열기 전에는 알아채기 어렵다. 그래서 여기서 막는다.
    """
    start = html.index("<script>\nconst DATA")
    script = html[start:html.index("</script>", start)]

    problems = []
    # 이스케이프가 벗겨지면 '.split('  처럼 줄 끝에서 문자열이 열린 채 끝난다.
    # 정규식 안의 따옴표를 오탐하지 않도록 '줄 끝이 따옴표' 인 경우만 본다.
    for num, line in enumerate(script.splitlines(), 1):
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("//"):
            continue
        last = stripped[-1]
        if last in ("'", '"') and stripped.count(last) % 2 == 1:
            problems.append(f"{num}행에서 문자열이 닫히지 않았습니다: {stripped.strip()[:60]}")
            break
    for bad, name in ((chr(0x2028), "U+2028"), (chr(0x2029), "U+2029")):
        if bad in script:
            problems.append(f"{name} 문자가 들어 있습니다 (JS 파싱 오류 유발)")
    if "</script" in script:
        problems.append("데이터에 </script 가 들어 있어 태그가 조기 종료됩니다")

    if problems:
        raise RuntimeError("스냅샷 생성물 검사 실패 — " + "; ".join(problems))


def write(path: str) -> str:
    import pathlib
    html = build_html()
    _check(html)
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return str(p)


# ─────────────────────────────────────────────────────────── 템플릿

_HEAD = """<title>거시 브리핑 보드</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@600;700&display=swap">
<style>
:root {
  --bg:#f4f6f8; --surface:#ffffff; --surface-2:#eef1f5; --line:#d8dee6;
  --text:#141c26; --dim:#5f6d7e; --faint:#8b98a6;
  --accent:#2f5fd0; --accent-soft:#e4ebfb;
  --up:#c8323f; --down:#2069b4; --flat:#7b8794;
  --hawk:#c8323f; --dove:#2069b4;
  --star:#b07219;
  --shadow:0 1px 2px rgba(20,28,38,.06), 0 6px 20px rgba(20,28,38,.05);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:#0d1319; --surface:#141c24; --surface-2:#1b242e; --line:#27323d;
    --text:#e4ebf2; --dim:#93a2b1; --faint:#6b7a89;
    --accent:#6d9bf1; --accent-soft:#1a2942;
    --up:#ef6a72; --down:#5aa2e8; --flat:#7b8794;
    --hawk:#ef6a72; --dove:#5aa2e8;
    --star:#d9a441;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 6px 20px rgba(0,0,0,.25);
  }
}
:root[data-theme="dark"] {
  --bg:#0d1319; --surface:#141c24; --surface-2:#1b242e; --line:#27323d;
  --text:#e4ebf2; --dim:#93a2b1; --faint:#6b7a89;
  --accent:#6d9bf1; --accent-soft:#1a2942;
  --up:#ef6a72; --down:#5aa2e8; --flat:#7b8794;
  --hawk:#ef6a72; --dove:#5aa2e8;
  --star:#d9a441;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 6px 20px rgba(0,0,0,.25);
}

* { box-sizing:border-box; }
body {
  background:var(--bg); color:var(--text); margin:0;
  font-family:"IBM Plex Sans KR","Malgun Gothic",system-ui,sans-serif;
  font-size:15px; line-height:1.6;
}
.page { max-width:1080px; margin:0 auto; padding:40px 22px 64px; }
.num { font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; }

/* ── 머리말 */
.masthead { border-bottom:2px solid var(--text); padding-bottom:16px; margin-bottom:8px; }
.eyebrow {
  font-size:11px; letter-spacing:.18em; text-transform:uppercase;
  color:var(--dim); margin-bottom:10px;
}
.masthead h1 {
  font-family:"Noto Serif KR",serif; font-weight:700;
  font-size:clamp(28px,5vw,40px); line-height:1.15; margin:0;
  letter-spacing:-.02em; text-wrap:balance;
}
.stamp {
  display:flex; flex-wrap:wrap; gap:6px 18px; justify-content:space-between;
  font-size:12px; color:var(--dim); padding:10px 0 0;
}

/* ── 섹션 */
section { margin-top:44px; }
.sec-head { display:flex; align-items:baseline; gap:12px; margin-bottom:14px; }
.sec-head h2 {
  font-family:"Noto Serif KR",serif; font-weight:600; font-size:19px;
  margin:0; letter-spacing:-.01em;
}
.sec-head .hint { font-size:12px; color:var(--faint); }

/* ── KPI */
.cat { margin-bottom:22px; }
.cat-label {
  font-size:11px; letter-spacing:.14em; color:var(--dim);
  text-transform:uppercase; margin-bottom:8px;
}
.kpis { display:grid; gap:1px; background:var(--line);
  grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  border:1px solid var(--line); border-radius:8px; overflow:hidden; }
.kpi { background:var(--surface); padding:13px 15px; display:flex;
  flex-direction:column; gap:5px; }
.kpi-name { font-size:12.5px; color:var(--dim); }
.kpi-val { font-size:23px; font-weight:600; letter-spacing:-.01em; }
.kpi-val .u { font-size:12px; color:var(--faint); margin-left:3px; font-weight:400; }
.kpi-foot { display:flex; justify-content:space-between; align-items:baseline;
  font-size:12px; gap:8px; }
.chg { font-weight:600; }
.up { color:var(--up); } .down { color:var(--down); } .flat { color:var(--flat); }
.asof { color:var(--faint); font-size:11px; }

/* ── 컨트롤 */
.controls { display:flex; flex-wrap:wrap; gap:14px; align-items:center; margin-bottom:12px; }
.seg { display:inline-flex; border:1px solid var(--line); border-radius:7px;
  overflow:hidden; background:var(--surface); }
.seg button { background:none; border:0; color:var(--dim); padding:6px 12px;
  font:inherit; font-size:12.5px; cursor:pointer; }
.seg button + button { border-left:1px solid var(--line); }
.seg button[aria-pressed="true"] { background:var(--accent); color:#fff; }
.seg button:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip { background:var(--surface); border:1px solid var(--line); color:var(--dim);
  border-radius:999px; padding:5px 12px; font:inherit; font-size:12.5px; cursor:pointer; }
.chip[aria-pressed="true"] { border-color:var(--accent); background:var(--accent-soft);
  color:var(--text); }
.chip:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }

.chart { height:400px; background:var(--surface); border:1px solid var(--line);
  border-radius:10px; box-shadow:var(--shadow); }

/* ── 일정 */
.cal { display:grid; gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:8px; overflow:hidden; }
.row { background:var(--surface); display:grid; grid-template-columns:104px 1fr auto;
  gap:12px; align-items:center; padding:11px 15px; }
.row.today { background:var(--accent-soft); }
.row.past { color:var(--faint); }
.row .d { font-size:12.5px; color:var(--dim); }
.row.today .d { color:var(--accent); font-weight:600; }
.row .t { font-size:14px; }
.row .s { font-size:12px; color:var(--star); letter-spacing:1px; white-space:nowrap; }
.row.past .s { color:var(--faint); }

/* ── 발언 */
.tone-bar { display:flex; gap:16px; font-size:12.5px; color:var(--dim); }
.feed { display:grid; gap:10px; grid-template-columns:repeat(auto-fill,minmax(310px,1fr)); }
.sp { background:var(--surface); border:1px solid var(--line); border-radius:10px;
  padding:14px 15px; display:flex; flex-direction:column; gap:7px; }
.sp-top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.sp-who { font-size:12.5px; font-weight:600; }
.sp-who span { font-weight:400; color:var(--dim); margin-left:5px; }
.sp h3 { font-size:14px; margin:0; line-height:1.45; font-weight:500; }
.sp h3 a { color:var(--text); text-decoration:none; }
.sp h3 a:hover { color:var(--accent); text-decoration:underline; }
.sp-date { font-size:11.5px; color:var(--faint); }
.tone { font-size:10.5px; padding:2px 9px; border-radius:999px;
  border:1px solid var(--line); color:var(--dim); white-space:nowrap; }
.tone.hawkish { border-color:var(--hawk); color:var(--hawk); }
.tone.dovish { border-color:var(--dove); color:var(--dove); }

.doc { background:var(--surface); border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; margin-bottom:10px; }
.doc summary { cursor:pointer; display:flex; flex-wrap:wrap; gap:8px;
  align-items:center; list-style:none; }
.doc summary::-webkit-details-marker { display:none; }
.doc summary::before { content:"▸"; color:var(--faint); font-size:12px; }
.doc[open] summary::before { content:"▾"; }
.doc-date { font-size:12.5px; color:var(--dim); }
.doc-kind { font-size:11px; color:var(--faint); border:1px solid var(--line);
  border-radius:4px; padding:1px 6px; }
.doc-head { font-size:14px; font-weight:500; flex:1 1 240px; }
.doc-reason { font-size:12px; color:var(--dim); margin:10px 0 0; }
.doc-body { font-size:13.5px; color:var(--dim); line-height:1.7; margin-top:12px;
  white-space:pre-wrap; }
.doc-foot { margin:12px 0 0; font-size:12px; }
.doc-foot a { color:var(--accent); }
.kpi-fc { margin-top:6px; padding-top:6px; border-top:1px dashed var(--line);
  font-size:11.5px; color:var(--dim); }
.kpi-fc b { color:var(--star); }
.fc { color:var(--star); }
.ok { color:#2e8b57; }
footer { margin-top:52px; padding-top:16px; border-top:1px solid var(--line);
  font-size:11.5px; color:var(--faint); }
footer p { margin:4px 0; }

@media (max-width:560px) {
  .row { grid-template-columns:82px 1fr; }
  .row .s { grid-column:2; }
}
@media (prefers-reduced-motion:reduce) { * { animation:none !important; transition:none !important; } }
</style>
"""

_BODY = """<div class="page">

<header class="masthead">
  <div class="eyebrow">Macro Snapshot · 한국은행 · 미 재무부 · 연준 · FRED</div>
  <h1>거시 브리핑 보드</h1>
</header>
<div class="stamp">
  <span id="stampTime"></span>
  <span>이 페이지는 발행 시점의 값을 담은 스냅샷입니다</span>
</div>

<section>
  <div class="sec-head"><h2>지표 현황</h2>
    <span class="hint">변화는 직전 관측 대비 · 금리는 bp, 그 밖의 % 지표는 %p</span></div>
  <div id="kpis"></div>
</section>

<section id="fcSection" hidden>
  <div class="sec-head"><h2>전망치</h2>
    <span class="hint">시장 컨센서스가 아니라 공개된 공식 전망입니다 — 출처를 함께 표시합니다</span></div>
  <div class="cal" id="fcNext"></div>
  <div class="cal" id="fcYear" style="margin-top:14px"></div>
</section>

<section>
  <div class="sec-head"><h2>과거 추이</h2>
    <span class="hint">지표를 눌러 겹쳐 보세요 (최대 4개)</span></div>
  <div class="controls">
    <div class="seg" id="rangeSeg" role="group" aria-label="기간">
      <button data-r="1Y">1Y</button><button data-r="3Y">3Y</button>
      <button data-r="5Y" aria-pressed="true">5Y</button>
      <button data-r="10Y">10Y</button><button data-r="MAX">MAX</button>
    </div>
    <div class="chips" id="chips"></div>
  </div>
  <div class="chart" id="histChart"></div>
</section>

<section>
  <div class="sec-head"><h2>미 국채 수익률곡선</h2>
    <span class="hint">최신 · 1개월 전 · 1년 전 비교</span></div>
  <div class="chart" id="curveChart" style="height:340px"></div>
</section>

<section>
  <div class="sec-head"><h2>발표일정</h2>
    <span class="hint">FOMC · 금통위 · 미국 주요 지표</span></div>
  <div class="controls">
    <div class="seg" id="calSeg" role="group" aria-label="범위">
      <button data-c="upcoming" aria-pressed="true">예정</button>
      <button data-c="past">지난 일정</button>
    </div>
  </div>
  <div class="cal" id="cal"></div>
</section>

<section id="docSection" hidden>
  <div class="sec-head"><h2>연준 회의록 · 성명</h2>
    <span class="hint">원문을 정책·물가·고용·향후 방향으로 압축한 한글 요약입니다</span></div>
  <div id="docs"></div>
</section>

<section>
  <div class="sec-head"><h2>주요 인사 발언</h2></div>
  <div class="controls"><div class="tone-bar" id="toneBar"></div></div>
  <div class="feed" id="feed"></div>
</section>

<footer>
  <p>출처 — 미 재무부 일별 국채 수익률곡선 · 연방준비제도 · FRED · 한국은행(ECOS, 통화정책방향 결정회의)</p>
  <p>매파/비둘기파 태그는 원문 키워드 기반 휴리스틱입니다. 해석 보조용이며 원문 확인을 대체하지 않습니다.</p>
  <p>공개 데이터를 취합·표시하는 정보 도구이며 투자 자문이 아닙니다.</p>
</footer>

</div>
"""

_SCRIPT = """
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const RATE_CATS = new Set(['금리','정책금리']);
const WD = ['일','월','화','수','목','금','토'];

function fmtNum(v, d) {
  return v == null ? '—' : v.toLocaleString('ko-KR',
    {minimumFractionDigits: d, maximumFractionDigits: d});
}
function fmtChange(v, unit, dec, cat) {
  if (v == null) return {t:'—', c:'flat'};
  if (v === 0) return {t:'보합', c:'flat'};
  const c = v > 0 ? 'up' : 'down', sign = v > 0 ? '+' : '';
  if (unit === '%' || unit === '%p') {
    return RATE_CATS.has(cat)
      ? {t:`${sign}${Math.round(v*100)}bp`, c}
      : {t:`${sign}${fmtNum(v,2)}%p`, c};
  }
  return {t:`${sign}${fmtNum(v, dec)}`, c};
}

$('#stampTime').textContent = '기준 ' + DATA.generated_at;

/* ── KPI ─────────────────────────────────────────── */
(function renderKpis() {
  const order = ['정책금리','금리','물가','고용','시장'];
  const groups = {};
  DATA.indicators.forEach(i => (groups[i.category] ||= []).push(i));
  const cats = [...new Set([...order, ...Object.keys(groups)])].filter(c => groups[c]);

  $('#kpis').innerHTML = cats.map(cat => `
    <div class="cat">
      <div class="cat-label">${esc(cat)}</div>
      <div class="kpis">${groups[cat].map(i => {
        const dec = i.decimals == null ? 2 : i.decimals;
        const ch = fmtChange(i.change, i.unit, dec, i.category);
        return `<div class="kpi">
          <div class="kpi-name">${esc(i.name_ko)}</div>
          <div class="kpi-val num">${fmtNum(i.latest, dec)}<span class="u">${esc(i.unit||'')}</span></div>
          <div class="kpi-foot">
            <span class="chg num ${ch.c}">${ch.t}</span>
            <span class="asof num">${esc(i.latest_date||'')}</span>
          </div>
          ${i.forecast ? `<div class="kpi-fc">다음 발표 예상
            <b class="num">${fmtNum(i.forecast.value, dec)}${esc(i.unit||'')}</b>
            <span class="asof num">${esc(i.forecast.target_period.slice(0,7))}</span></div>` : ''}
        </div>`;
      }).join('')}</div>
    </div>`).join('');
})();

/* ── 시계열 ──────────────────────────────────────── */
const RANGE_DAYS = {'1Y':365,'3Y':1095,'5Y':1825,'10Y':3650,'MAX':0};
let range = '5Y';
let picked = ['US10Y','US2Y'].filter(c => DATA.series[c]);
if (!picked.length) picked = Object.keys(DATA.series).slice(0,2);

const PALETTE = ['#2f5fd0','#c8323f','#2e8b57','#b07219','#7a4fbf','#158a92'];
const isDark = () => {
  const t = document.documentElement.getAttribute('data-theme');
  if (t) return t === 'dark';
  return matchMedia('(prefers-color-scheme: dark)').matches;
};
const themeColors = () => isDark()
  ? {text:'#93a2b1', line:'#27323d', pal:['#6d9bf1','#ef6a72','#57b98a','#d9a441','#a988e8','#3fb6bf']}
  : {text:'#5f6d7e', line:'#d8dee6', pal:PALETTE};

const hist = echarts.init($('#histChart'));
const curve = echarts.init($('#curveChart'));
addEventListener('resize', () => { hist.resize(); curve.resize(); });

function cutoff() {
  const d = RANGE_DAYS[range];
  if (!d) return '1900-01-01';
  const t = new Date(); t.setDate(t.getDate() - d);
  return t.toISOString().slice(0,10);
}

function renderHist() {
  const tc = themeColors();
  const from = cutoff();
  const units = [...new Set(picked.map(c => DATA.series[c].unit || ''))];
  const axis = {
    axisLine:{lineStyle:{color:tc.line}},
    axisLabel:{color:tc.text, fontSize:11},
    splitLine:{lineStyle:{color:tc.line, type:'dashed'}},
  };
  const yAxis = [{type:'value', scale:true, name:units[0]||'', nameTextStyle:{color:tc.text}, ...axis}];
  if (units.length > 1) yAxis.push({type:'value', scale:true, name:units[1]||'',
    nameTextStyle:{color:tc.text}, ...axis, splitLine:{show:false}});

  hist.setOption({
    backgroundColor:'transparent',
    grid:{left:60, right:units.length>1?62:24, top:44, bottom:40},
    tooltip:{trigger:'axis'},
    legend:{top:8, textStyle:{color:tc.text, fontSize:12}, icon:'roundRect'},
    xAxis:{type:'time', ...axis, splitLine:{show:false}},
    yAxis,
    series: picked.map((code, i) => {
      const s = DATA.series[code];
      return {
        name:`${s.name}${s.unit?' ('+s.unit+')':''}`,
        type:'line', showSymbol:false, sampling:'lttb',
        yAxisIndex: units.length>1 && (s.unit||'')===units[1] ? 1 : 0,
        lineStyle:{width:1.8}, itemStyle:{color:tc.pal[i % tc.pal.length]},
        data: s.points.filter(p => p[0] >= from),
      };
    }),
  }, true);
}

function renderChips() {
  $('#chips').innerHTML = Object.entries(DATA.series).map(([code, s]) =>
    `<button class="chip" data-code="${code}" aria-pressed="${picked.includes(code)}">${esc(s.name)}</button>`
  ).join('');
}

$('#chips').addEventListener('click', e => {
  const btn = e.target.closest('.chip'); if (!btn) return;
  const code = btn.dataset.code, i = picked.indexOf(code);
  if (i >= 0) { if (picked.length === 1) return; picked.splice(i,1); }
  else { if (picked.length >= 4) return; picked.push(code); }
  renderChips(); renderHist();
});

$('#rangeSeg').addEventListener('click', e => {
  const btn = e.target.closest('button'); if (!btn) return;
  range = btn.dataset.r;
  [...e.currentTarget.children].forEach(b => b.setAttribute('aria-pressed', b === btn));
  renderHist();
});

function renderCurve() {
  const tc = themeColors();
  const axis = {
    axisLine:{lineStyle:{color:tc.line}},
    axisLabel:{color:tc.text, fontSize:11},
    splitLine:{lineStyle:{color:tc.line, type:'dashed'}},
  };
  curve.setOption({
    backgroundColor:'transparent',
    grid:{left:56, right:24, top:44, bottom:40},
    tooltip:{trigger:'axis', valueFormatter: v => v==null ? '—' : v.toFixed(2)+'%'},
    legend:{top:8, textStyle:{color:tc.text, fontSize:12}, icon:'roundRect'},
    xAxis:{type:'category', data:DATA.curve.labels, ...axis, splitLine:{show:false}, name:'만기'},
    yAxis:{type:'value', scale:true, name:'%', nameTextStyle:{color:tc.text}, ...axis},
    series: DATA.curve.lines.map((ln,i) => ({
      name:`${ln.label} (${ln.date||''})`, type:'line', symbol:'circle', symbolSize:6,
      connectNulls:true, lineStyle:{width:2, type: i?'dashed':'solid'},
      itemStyle:{color:tc.pal[i % tc.pal.length]}, data:ln.values,
    })),
  }, true);
}

/* ── 전망치 ──────────────────────────────────────── */
(function renderForecasts() {
  const nextRows = DATA.indicators.filter(i => i.forecast);
  const yearly = DATA.forecast_yearly || [];
  if (!nextRows.length && !yearly.length) return;
  document.getElementById('fcSection').hidden = false;

  document.getElementById('fcNext').innerHTML = nextRows.map(i => {
    const dec = i.decimals == null ? 2 : i.decimals;
    return `<div class="row">
      <span class="d num">${esc(i.forecast.target_period.slice(0,7))}</span>
      <span class="t">${esc(i.name_ko)}
        <b class="num">${fmtNum(i.forecast.value, dec)}${esc(i.unit||'')}</b>
        <span class="asof">실측 ${fmtNum(i.latest, dec)} (${esc(i.latest_date||'')})</span></span>
      <span class="asof">${esc(i.forecast.source)}</span>
    </div>`;
  }).join('');

  const byCode = {};
  yearly.forEach(f => (byCode[f.indicator_code] ||= []).push(f));
  document.getElementById('fcYear').innerHTML = Object.values(byCode).map(list => {
    const head = list[0];
    const cells = list.map(f =>
      `${f.target_period.slice(0,4)}년 <b class="num">${f.value.toFixed(2)}</b>`).join(' · ');
    return `<div class="row">
      <span class="d">${esc((head.name_ko||head.indicator_code).slice(0,12))}</span>
      <span class="t">${cells}</span>
      <span class="asof">${esc(head.source)}</span>
    </div>`;
  }).join('');
})();

/* ── 일정 ────────────────────────────────────────── */
let calMode = 'upcoming';
function renderCal() {
  const today = DATA.today;
  let rows = DATA.events.filter(e =>
    calMode === 'upcoming' ? e.event_date >= today : e.event_date < today);
  if (calMode === 'past') rows = rows.slice(-12).reverse();
  else rows = rows.slice(0, 14);

  if (!rows.length) { $('#cal').innerHTML =
    '<div class="row"><span class="t">표시할 일정이 없습니다.</span></div>'; return; }

  $('#cal').innerHTML = rows.map(e => {
    const d = new Date(e.event_date + 'T00:00:00');
    const cls = e.event_date === today ? 'today' : (e.event_date < today ? 'past' : '');
    const label = e.event_date === today ? '오늘'
      : `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} (${WD[d.getDay()]})`;
    return `<div class="row ${cls}">
      <span class="d num">${label}</span>
      <span class="t">${esc(e.title)}${e.event_time ? ` <span class="asof">${esc(e.event_time)}</span>` : ''}${e.forecast ? ` <b class="num fc">예상 ${esc(e.forecast)}</b>` : ''}${e.actual ? ` <b class="num ok">실제 ${esc(e.actual)}</b>` : ''}</span>
      <span class="s">${'★'.repeat(e.importance||1)}</span>
    </div>`;
  }).join('');
}
$('#calSeg').addEventListener('click', e => {
  const btn = e.target.closest('button'); if (!btn) return;
  calMode = btn.dataset.c;
  [...e.currentTarget.children].forEach(b => b.setAttribute('aria-pressed', b === btn));
  renderCal();
});

const TONE_KO = {hawkish:'매파', dovish:'비둘기파', neutral:'중립'};
// 요약문의 문단 구분자. 이 파일은 파이썬 문자열 안에 들어가므로
// JS 소스에 백슬래시 이스케이프를 직접 쓰지 않고 코드포인트로 만든다.
const BLANK_LINE = String.fromCharCode(10, 10);

/* ── 회의록 ──────────────────────────────────────── */
(function renderDocs() {
  const docs = DATA.documents || [];
  if (!docs.length) return;
  document.getElementById('docSection').hidden = false;
  const KIND = { minutes: '회의록', statement: '성명' };
  document.getElementById('docs').innerHTML = docs.map(d => {
    const parts = (d.summary_ko || '').split(BLANK_LINE);
    const headline = parts[0] || '';
    const detail = parts.slice(1).join(BLANK_LINE);
    return `<details class="doc">
      <summary>
        <span class="doc-date num">${esc(d.meeting_date)}</span>
        <span class="doc-kind">${KIND[d.doc_type] || d.doc_type}</span>
        ${d.tone ? `<span class="tone ${d.tone}">${TONE_KO[d.tone] || d.tone}</span>` : ''}
        <span class="doc-head">${esc(headline)}</span>
      </summary>
      ${d.tone_reason ? `<p class="doc-reason">${esc(d.tone_reason)}</p>` : ''}
      <div class="doc-body">${esc(detail)}</div>
      <p class="doc-foot"><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">원문 보기</a></p>
    </details>`;
  }).join('');
})();

/* ── 발언 ────────────────────────────────────────── */
$('#toneBar').innerHTML =
  `최근 30일 &nbsp; 매파 <b class="up">${DATA.tone_stats.hawkish}</b>` +
  ` · 비둘기파 <b class="down">${DATA.tone_stats.dovish}</b>` +
  ` · 중립 <b>${DATA.tone_stats.neutral}</b>`;

$('#feed').innerHTML = DATA.speeches.map(s => `
  <article class="sp">
    <div class="sp-top">
      <div class="sp-who">${esc(s.speaker)}<span>${esc(s.role||'')}</span></div>
      <span class="tone ${s.tone}">${TONE_KO[s.tone]||s.tone}</span>
    </div>
    <h3><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a></h3>
    <div class="sp-date num">${esc((s.published_at||'').slice(0,10))} · ${esc(s.org||'')}</div>
  </article>`).join('');

/* ── 기동 ────────────────────────────────────────── */
renderChips(); renderHist(); renderCurve(); renderCal();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  renderHist(); renderCurve();
});
"""
