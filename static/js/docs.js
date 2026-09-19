/* 연준 회의록·성명 한글 요약 */
const DocView = {
  state: { type: '', expanded: new Set() },

  async load() {
    const params = new URLSearchParams({ limit: '12' });
    if (this.state.type) params.set('doc_type', this.state.type);
    const data = await API.get('/api/documents?' + params.toString());
    this.renderStatus(data);
    this.render(data.documents);
  },

  renderStatus(data) {
    const el = document.getElementById('docStatus');
    if (!data.translator_ready) {
      el.innerHTML = `<span class="doc__pending">한글 요약 대기 ${data.pending}건 —
        .env 에 ANTHROPIC_API_KEY 를 넣으면 처리됩니다</span>`;
    } else if (data.pending) {
      el.innerHTML = `<span class="doc__pending">한글 요약 대기 ${data.pending}건</span>`;
    } else {
      el.innerHTML = '';
    }
  },

  render(docs) {
    const el = document.getElementById('docList');
    if (!docs.length) {
      el.innerHTML = '<div class="empty">수집된 문서가 없습니다.</div>';
      return;
    }
    const KIND = { minutes: '회의록', statement: '성명' };
    el.innerHTML = docs.map(d => {
      const open = this.state.expanded.has(d.uid);
      const body = d.summary_ko || '';
      // 첫 줄(헤드라인)과 본문을 분리해 접힌 상태에서도 요지가 보이게 한다
      const [headline, ...rest] = body.split('\n\n');
      const detail = rest.join('\n\n');
      return `
      <article class="doc">
        <div class="doc__top">
          <h3 class="doc__title">${esc(d.meeting_date)} FOMC
            <span class="doc__kind">${KIND[d.doc_type] || d.doc_type}</span></h3>
          ${d.tone ? `<span class="tone tone--${d.tone}">${TONE_LABEL[d.tone] || d.tone}</span>` : ''}
        </div>
        ${headline ? `<p class="doc__head">${esc(headline)}</p>` : ''}
        ${d.tone_reason ? `<p class="doc__reason">${esc(d.tone_reason)}</p>` : ''}
        ${open && detail ? `<div class="doc__body">${esc(detail)}</div>` : ''}
        <div class="doc__foot">
          ${detail ? `<button class="doc__more" data-uid="${esc(d.uid)}">
            ${open ? '접기' : '전문 요약 보기'}</button>` : ''}
          ${!d.summary_ko ? '<span class="doc__pending">한글 요약 대기 중</span>' : ''}
          <a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">원문 보기</a>
        </div>
      </article>`;
    }).join('');

    el.querySelectorAll('.doc__more').forEach(btn => {
      btn.addEventListener('click', () => {
        const uid = btn.dataset.uid;
        if (this.state.expanded.has(uid)) this.state.expanded.delete(uid);
        else this.state.expanded.add(uid);
        this.load();
      });
    });
  },
};
