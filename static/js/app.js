/* 앱 부트스트랩 — 탭 전환, KPI 렌더, 이벤트 배선 */
const App = {
  summary: [],
  selected: ['US10Y', 'US2Y'],
  range: '5Y',
  loaded: { history: false, curve: false, calendar: false, speeches: false, docs: false },

  async init() {
    this.bindTabs();
    this.bindControls();
    await this.loadOverview();
    this.loadStatus();
    setInterval(() => this.loadStatus(), 60000);
  },

  /* ───────── 탭 */
  bindTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('is-active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('is-active'));
        tab.classList.add('is-active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('is-active');
        this.onTab(tab.dataset.tab);
      });
    });
  },

  /* 탭은 처음 열릴 때만 로드한다 (차트는 보이는 시점에 init 해야 크기가 잡힌다) */
  async onTab(name) {
    if (name === 'history' && !this.loaded.history) {
      Charts.initHistory(document.getElementById('historyChart'));
      this.renderChips();
      await this.loadHistory();
      this.loaded.history = true;
    } else if (name === 'history') {
      Charts.history.resize();
    }
    if (name === 'curve' && !this.loaded.curve) {
      Charts.initCurve(document.getElementById('curveChart'));
      Charts.renderCurve(await API.curve());
      this.loaded.curve = true;
    } else if (name === 'curve') {
      Charts.curve.resize();
    }
    if (name === 'calendar' && !this.loaded.calendar) {
      await CalendarView.load();
      this.loaded.calendar = true;
    }
    if (name === 'speeches' && !this.loaded.speeches) {
      await SpeechView.load();
      this.loaded.speeches = true;
    }
    if (name === 'docs' && !this.loaded.docs) {
      await DocView.load();
      this.loaded.docs = true;
    }
  },

  /* ───────── 지표 현황 */
  async loadOverview() {
    const data = await API.summary();
    this.summary = data.indicators;
    this.renderKpis();
  },

  renderKpis() {
    const groups = {};
    for (const ind of this.summary) (groups[ind.category] ||= []).push(ind);

    const order = ['정책금리', '금리', '물가', '고용', '시장'];
    const keys = [...new Set([...order, ...Object.keys(groups)])].filter(k => groups[k]);

    document.getElementById('kpiGroups').innerHTML = keys.map(cat => `
      <section class="group">
        <h2 class="group__title">${esc(cat)}</h2>
        <div class="kpis">${groups[cat].map(i => this.kpiCard(i)).join('')}</div>
      </section>`).join('');
  },

  kpiCard(i) {
    if (!i.has_data) {
      const needsKey = i.source === 'fred' || i.source === 'ecos';
      return `
        <div class="kpi kpi--muted">
          <div class="kpi__name">${esc(i.name_ko)}</div>
          <div class="kpi__value">—</div>
          <div class="kpi__row">
            <span class="kpi__need-key">
              ${needsKey ? `${i.source.toUpperCase()} API 키 필요` : '데이터 없음'}
            </span>
          </div>
        </div>`;
    }
    const chg = FMT.change(i.change, i.unit, i.decimals, i.category);
    const yoy = FMT.change(i.yoy_change, i.unit, i.decimals, i.category);
    return `
      <div class="kpi">
        <div class="kpi__name">${esc(i.name_ko)}</div>
        <div class="kpi__value">${FMT.num(i.latest, i.decimals)}<span class="kpi__unit">${esc(i.unit || '')}</span></div>
        <div class="kpi__row">
          <span class="kpi__chg ${chg.cls}">${chg.text}</span>
          <span class="kpi__date${i.stale ? ' kpi__date--stale' : ''}"
                ${i.stale ? `title="${i.lag_days}일째 갱신되지 않았습니다"` : ''}>
            ${FMT.date(i.latest_date)}${i.stale ? ' ⚠' : ''}
          </span>
        </div>
        <div class="kpi__row">
          <span class="kpi__date">1년 전 대비</span>
          <span class="kpi__chg ${yoy.cls}">${yoy.text}</span>
        </div>
        ${i.forecast ? `<div class="kpi__fc" title="${esc(i.forecast.source)}">
          다음 발표 예상 <b>${FMT.num(i.forecast.value, i.decimals)}${esc(i.unit||'')}</b>
          <span class="kpi__date">${i.forecast.target_period.slice(0,7)}</span>
        </div>` : ''}
      </div>`;
  },

  /* ───────── 과거 추이 */
  renderChips() {
    const withData = this.summary.filter(i => i.has_data);
    document.getElementById('seriesChips').innerHTML = withData.map(i => `
      <button class="chip${this.selected.includes(i.code) ? ' is-active' : ''}"
              data-code="${i.code}">${esc(i.name_ko)}</button>`).join('');

    document.querySelectorAll('#seriesChips .chip').forEach(chip => {
      chip.addEventListener('click', async () => {
        const code = chip.dataset.code;
        const idx = this.selected.indexOf(code);
        if (idx >= 0) {
          if (this.selected.length === 1) return;     // 최소 1개는 남긴다
          this.selected.splice(idx, 1);
        } else {
          if (this.selected.length >= 4) return;      // 최대 4개
          this.selected.push(code);
        }
        this.renderChips();
        await this.loadHistory();
      });
    });
  },

  async loadHistory() {
    Charts.renderHistory(await API.series(this.selected, this.range));
  },

  /* ───────── 컨트롤 */
  bindControls() {
    segmented('#rangeToggle', async btn => {
      this.range = btn.dataset.range;
      await this.loadHistory();
    });
    segmented('#countryToggle', btn => {
      CalendarView.state.country = btn.dataset.country;
      CalendarView.load();
    });
    segmented('#importanceToggle', btn => {
      CalendarView.state.importance = Number(btn.dataset.imp);
      CalendarView.load();
    });
    segmented('#docTypeToggle', btn => {
      DocView.state.type = btn.dataset.type;
      DocView.load();
    });
    segmented('#toneToggle', btn => {
      SpeechView.state.tone = btn.dataset.tone;
      SpeechView.load();
    });
    document.getElementById('prevMonth').addEventListener('click', () => CalendarView.shiftMonth(-1));
    document.getElementById('nextMonth').addEventListener('click', () => CalendarView.shiftMonth(1));

    document.getElementById('refreshBtn').addEventListener('click', async e => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = '수집 중…';
      await API.refresh();
      // 수집은 백그라운드에서 돈다 — 잠시 뒤 화면을 다시 채운다
      setTimeout(async () => {
        await this.loadOverview();
        this.loaded = { history: false, curve: false, calendar: false, speeches: false, docs: false };
        await this.loadStatus();
        btn.disabled = false;
        btn.textContent = '지금 갱신';
      }, 6000);
    });
  },

  /* ───────── 수집기 상태 */
  async loadStatus() {
    const data = await API.status();
    const label = { ok: '정상', error: '실패', skipped: '건너뜀', running: '수집 중' };
    document.getElementById('statusBadges').innerHTML = data.runs.map(r => `
      <span class="badge badge--${r.status}"
            title="${esc(r.message || '')} (${esc(r.finished_at || r.started_at)})">
        ${esc(r.collector)} · ${label[r.status] || r.status}
      </span>`).join('');
  },
};

function segmented(sel, handler) {
  const root = document.querySelector(sel);
  if (!root) return;
  root.querySelectorAll('button').forEach(btn => {
    btn.addEventListener('click', () => {
      root.querySelectorAll('button').forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      handler(btn);
    });
  });
}

document.addEventListener('DOMContentLoaded', () => App.init());
