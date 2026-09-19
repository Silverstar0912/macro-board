/* 발표일정 — 다가오는 7일 리스트 + 월간 그리드 */
const CalendarView = {
  state: { country: '', importance: 1, cursor: new Date() },
  cache: [],

  async load() {
    const first = new Date(this.state.cursor.getFullYear(), this.state.cursor.getMonth(), 1);
    const last = new Date(this.state.cursor.getFullYear(), this.state.cursor.getMonth() + 2, 0);
    const params = new URLSearchParams({
      start: iso(first), end: iso(last),
      min_importance: String(this.state.importance),
    });
    if (this.state.country) params.set('country', this.state.country);

    const data = await API.calendar(params.toString());
    this.cache = data.events;
    this.renderUpcoming(data.upcoming);
    this.renderMonth();
  },

  renderUpcoming(items) {
    const el = document.getElementById('upcomingList');
    const filtered = items.filter(e =>
      (!this.state.country || e.country === this.state.country) &&
      (e.importance || 1) >= this.state.importance);
    if (!filtered.length) {
      el.innerHTML = '<div class="empty">향후 7일간 예정된 일정이 없습니다.</div>';
      return;
    }
    el.innerHTML = filtered.map(e => `
      <div class="ev ev--imp${e.importance || 1}${e.is_today ? ' ev--today' : ''}">
        <div class="ev__top">
          <span>${e.event_date}${e.is_today ? ' · 오늘' : ''}</span>
          <span>${FMT.stars(e.importance)}</span>
        </div>
        <div class="ev__title">${esc(e.title)}</div>
        <div class="ev__meta">
          ${[e.country, e.event_time, e.source].filter(Boolean).map(esc).join(' · ')}
          ${e.forecast ? `<span class="ev__fc"> · 예상 ${esc(e.forecast)}</span>` : ''}
          ${e.actual ? `<span class="ev__actual"> · 실제 ${esc(e.actual)}</span>` : ''}
        </div>
      </div>`).join('');
  },

  renderMonth() {
    const cur = this.state.cursor;
    document.getElementById('monthLabel').textContent =
      `${cur.getFullYear()}년 ${cur.getMonth() + 1}월`;

    const byDate = {};
    for (const e of this.cache) (byDate[e.event_date] ||= []).push(e);

    const first = new Date(cur.getFullYear(), cur.getMonth(), 1);
    const start = new Date(first);
    start.setDate(1 - first.getDay());               // 그 주의 일요일부터 시작
    const today = iso(new Date());

    let html = ['일', '월', '화', '수', '목', '금', '토']
      .map(d => `<div class="month__dow">${d}</div>`).join('');

    for (let i = 0; i < 42; i++) {
      const day = new Date(start);
      day.setDate(start.getDate() + i);
      const key = iso(day);
      const out = day.getMonth() !== cur.getMonth();
      const evs = (byDate[key] || []).slice(0, 3);
      html += `
        <div class="month__cell${out ? ' month__cell--out' : ''}${key === today ? ' month__cell--today' : ''}">
          <div class="month__day">${day.getDate()}</div>
          ${evs.map(e => `<span class="month__ev month__ev--imp${e.importance || 1}"
              title="${esc(e.title)}">${esc(e.title)}</span>`).join('')}
          ${(byDate[key] || []).length > 3
            ? `<span class="month__day">+${byDate[key].length - 3}</span>` : ''}
        </div>`;
    }
    document.getElementById('monthGrid').innerHTML = html;
  },

  shiftMonth(delta) {
    this.state.cursor = new Date(
      this.state.cursor.getFullYear(), this.state.cursor.getMonth() + delta, 1);
    this.load();
  },
};

function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
