/* 주요 인사 발언 피드 */
const TONE_LABEL = { hawkish: '매파', dovish: '비둘기파', neutral: '중립' };

const SpeechView = {
  state: { tone: '' },

  async load() {
    const params = new URLSearchParams({ limit: '48' });
    if (this.state.tone) params.set('tone', this.state.tone);
    const data = await API.speeches(params.toString());
    this.renderStats(data.tone_stats);
    this.renderFeed(data.speeches);
  },

  renderStats(s) {
    document.getElementById('toneStats').innerHTML =
      `최근 30일 &nbsp; 매파 <b class="up">${s.hawkish}</b>` +
      ` · 비둘기파 <b class="down">${s.dovish}</b>` +
      ` · 중립 <b>${s.neutral}</b>`;
  },

  renderFeed(items) {
    const el = document.getElementById('speechList');
    if (!items.length) {
      el.innerHTML = '<div class="empty">표시할 발언이 없습니다.</div>';
      return;
    }
    el.innerHTML = items.map(s => `
      <article class="sp">
        <div class="sp__top">
          <div class="sp__who">${esc(s.speaker)}<span class="sp__role">${esc(s.role || '')}</span></div>
          <span class="tone tone--${s.tone}">${TONE_LABEL[s.tone] || s.tone}</span>
        </div>
        <h3 class="sp__title">
          <a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>
        </h3>
        ${s.summary ? `<p class="sp__summary">${esc(s.summary.slice(0, 180))}</p>` : ''}
        <div class="sp__date">${FMT.dateTime(s.published_at)} · ${esc(s.org || '')}</div>
      </article>`).join('');
  },
};
