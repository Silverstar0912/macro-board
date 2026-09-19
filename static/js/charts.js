/* ECharts 렌더러 — 시계열 차트와 수익률곡선 */
const THEME = {
  text: '#8b98a5',
  line: '#2a333f',
  palette: ['#4c9aff', '#f2555a', '#3fb950', '#f0a03c', '#a371f7', '#39c5cf'],
};

function baseGrid() {
  return { left: 58, right: 62, top: 42, bottom: 62 };
}

function axisCommon() {
  return {
    axisLine: { lineStyle: { color: THEME.line } },
    axisLabel: { color: THEME.text, fontSize: 11 },
    splitLine: { lineStyle: { color: THEME.line, type: 'dashed' } },
  };
}

const Charts = {
  history: null,
  curve: null,

  initHistory(el) {
    this.history = echarts.init(el, null, { renderer: 'canvas' });
    window.addEventListener('resize', () => this.history && this.history.resize());
    return this.history;
  },

  /* 단위가 다른 지표가 섞이면 두 번째 단위를 오른쪽 축으로 보낸다 */
  renderHistory(payload) {
    if (!this.history) return;
    const entries = Object.entries(payload.series);
    if (!entries.length) { this.history.clear(); return; }

    const units = [...new Set(entries.map(([, s]) => s.meta.unit || ''))];
    const axisOf = u => (units.length > 1 && u === units[1] ? 1 : 0);

    const series = entries.map(([code, s], i) => ({
      name: `${s.meta.name_ko} (${s.meta.unit || ''})`,
      type: 'line',
      showSymbol: false,
      smooth: false,
      sampling: 'lttb',
      yAxisIndex: axisOf(s.meta.unit || ''),
      lineStyle: { width: 1.8 },
      itemStyle: { color: THEME.palette[i % THEME.palette.length] },
      data: s.points,
    }));

    const yAxis = [{ type: 'value', scale: true, name: units[0] || '', ...axisCommon() }];
    if (units.length > 1) {
      yAxis.push({ type: 'value', scale: true, name: units[1] || '',
                   ...axisCommon(), splitLine: { show: false } });
    }

    this.history.setOption({
      backgroundColor: 'transparent',
      grid: baseGrid(),
      tooltip: { trigger: 'axis', backgroundColor: '#1c242e',
                 borderColor: '#2a333f', textStyle: { color: '#e6edf3', fontSize: 12 } },
      legend: { top: 8, textStyle: { color: THEME.text, fontSize: 12 }, icon: 'roundRect' },
      xAxis: { type: 'time', ...axisCommon(), splitLine: { show: false } },
      yAxis,
      dataZoom: [
        { type: 'inside' },
        { type: 'slider', height: 20, bottom: 14, borderColor: THEME.line,
          textStyle: { color: THEME.text, fontSize: 10 },
          fillerColor: 'rgba(76,154,255,0.12)' },
      ],
      series,
    }, true);
  },

  initCurve(el) {
    this.curve = echarts.init(el, null, { renderer: 'canvas' });
    window.addEventListener('resize', () => this.curve && this.curve.resize());
    return this.curve;
  },

  renderCurve(payload) {
    if (!this.curve) return;
    const series = payload.lines.map((ln, i) => ({
      name: `${ln.label} (${FMT.date(ln.date)})`,
      type: 'line',
      symbol: 'circle',
      symbolSize: 6,
      connectNulls: true,
      lineStyle: { width: 2, type: i === 0 ? 'solid' : 'dashed' },
      itemStyle: { color: THEME.palette[i % THEME.palette.length] },
      data: ln.values,
    }));
    this.curve.setOption({
      backgroundColor: 'transparent',
      grid: baseGrid(),
      tooltip: { trigger: 'axis', backgroundColor: '#1c242e',
                 borderColor: '#2a333f', textStyle: { color: '#e6edf3', fontSize: 12 },
                 valueFormatter: v => (v === null ? '—' : v.toFixed(2) + '%') },
      legend: { top: 8, textStyle: { color: THEME.text, fontSize: 12 }, icon: 'roundRect' },
      xAxis: { type: 'category', data: payload.labels, ...axisCommon(),
               splitLine: { show: false }, name: '만기' },
      yAxis: { type: 'value', scale: true, name: '%', ...axisCommon() },
      series,
    }, true);
  },
};
