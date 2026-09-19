/* API 클라이언트와 공용 포맷터 */
const API = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`${path} → ${res.status}`);
    return res.json();
  },
  post(path) { return fetch(path, { method: 'POST' }).then(r => r.json()); },

  summary:    ()             => API.get('/api/summary'),
  series:     (codes, range) => API.get(`/api/series?codes=${codes.join(',')}&range=${range}`),
  curve:      ()             => API.get('/api/curve'),
  calendar:   (q = '')       => API.get('/api/calendar' + (q ? '?' + q : '')),
  speeches:   (q = '')       => API.get('/api/speeches' + (q ? '?' + q : '')),
  status:     ()             => API.get('/api/status'),
  refresh:    ()             => API.post('/api/refresh'),
};

const FMT = {
  num(v, decimals = 2) {
    if (v === null || v === undefined) return '—';
    return v.toLocaleString('ko-KR', {
      minimumFractionDigits: decimals, maximumFractionDigits: decimals,
    });
  },
  /* 금리는 bp, 물가·고용 등 나머지 % 지표는 %p, 그 외는 원단위로 표기한다 */
  change(v, unit, decimals = 2, category = '') {
    if (v === null || v === undefined) return { text: '—', cls: 'flat' };
    const cls = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
    const sign = v > 0 ? '+' : '';
    if (unit === '%' || unit === '%p') {
      const isRate = category === '금리' || category === '정책금리';
      return isRate
        ? { text: `${sign}${Math.round(v * 100)}bp`, cls }
        : { text: `${sign}${FMT.num(v, 2)}%p`, cls };
    }
    return { text: `${sign}${FMT.num(v, decimals)}`, cls };
  },
  date(iso) { return iso ? iso.slice(0, 10) : '—'; },
  dateTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? iso.slice(0, 10)
      : `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  },
  stars(n) { return '★'.repeat(n || 1); },
};
