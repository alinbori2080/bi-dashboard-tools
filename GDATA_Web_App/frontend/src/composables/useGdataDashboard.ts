// @ts-nocheck
// GDATA 看板业务逻辑：从旧静态脚本迁移到前端工程源码。

let mounted = false;

export function mountGdataDashboard() {
  if (mounted) return;
  mounted = true;
const state = {
  status: null,
  runtime: null,
  activeReport: 'conversion',
    range: 'all',
    compareDimension: '日',
    customStart: '',
    customEnd: '',
    loading: false,
  sourceMode: 'feishu',
  sidePanelCollapsed: localStorage.getItem('gdataSidePanelCollapsed') !== 'false',
};

const els = {
  dataDir: document.querySelector('#dataDir'),
  refreshButton: document.querySelector('#refreshButton'),
  syncButton: document.querySelector('#syncButton'),
  exportButton: document.querySelector('#exportButton'),
  menuButton: document.querySelector('#menuButton'),
  sidePanelButton: document.querySelector('#sidePanelButton'),
  rangeTabs: document.querySelector('#rangeTabs'),
  sourceModeTabs: document.querySelector('#sourceModeTabs'),
    compareTabs: document.querySelector('#compareTabs'),
    customRange: document.querySelector('#customRange'),
    startDateInput: document.querySelector('#startDateInput'),
    endDateInput: document.querySelector('#endDateInput'),
    noticeBand: document.querySelector('#noticeBand'),
  reportTitle: document.querySelector('#reportTitle'),
  reportFormula: document.querySelector('#reportFormula'),
  lastRefresh: document.querySelector('#lastRefresh'),
  kpiGrid: document.querySelector('#kpiGrid'),
  kpiPeriod: document.querySelector('#kpiPeriod'),
  chartSubtitle: document.querySelector('#chartSubtitle'),
  denominatorLegend: document.querySelector('#denominatorLegend'),
  numeratorLegend: document.querySelector('#numeratorLegend'),
  chart: document.querySelector('#chart'),
  rowCount: document.querySelector('#rowCount'),
  tableHead: document.querySelector('#tableHead'),
  tableBody: document.querySelector('#tableBody'),
  runtimeInfo: document.querySelector('#runtimeInfo'),
  reportStats: document.querySelector('#reportStats'),
  sourceList: document.querySelector('#sourceList'),
  syncInfo: document.querySelector('#syncInfo'),
  messageList: document.querySelector('#messageList'),
};

function setLoading(loading) {
  state.loading = loading;
  els.refreshButton.disabled = loading;
  els.syncButton.disabled = loading || state.sourceMode === 'feishu';
  els.refreshButton.textContent = loading ? '刷新中...' : '刷新数据';
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { cache: 'no-store', ...options });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function exportTimestamp(date = new Date()) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}_${pad2(date.getHours())}点${pad2(date.getMinutes())}分`;
}

function safeFilePart(value) {
  return String(value || 'report')
    .trim()
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, '_')
    .replace(/\s+/g, ' ')
    .slice(0, 80) || 'report';
}

function nextExportFilename(reportTitle, extension) {
  const base = `${safeFilePart(reportTitle)}_${exportTimestamp()}`;
  const key = `gdata-export-${base}.${extension}`;
  const count = Number(localStorage.getItem(key) || '0') + 1;
  localStorage.setItem(key, String(count));
  const suffix = count === 1 ? '' : `_${pad2(count)}`;
  return `${base}${suffix}.${extension}`;
}

function csvCell(value) {
  const text = String(value ?? '');
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function csvText(columns, rows) {
  const lines = [
    columns.map(csvCell).join(','),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(',')),
  ];
  return `\ufeff${lines.join('\r\n')}`;
}

function downloadText(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function loadInitial() {
  try {
    const [status, runtime] = await Promise.all([
      fetchJson('/api/status'),
      fetchJson('/api/reports'),
    ]);
    state.status = status;
    state.runtime = runtime;
    state.sourceMode = runtime.sourceMode || status.sourceMode || 'feishu';
    render();
  } catch (error) {
    renderFatal(`页面初始化失败：${error.message}`);
  }
}

async function refreshReports() {
  setLoading(true);
  try {
    const runtime = await fetchJson('/api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sourceMode: state.sourceMode }),
    });
    state.runtime = runtime;
    state.status = runtime.status;
    state.sourceMode = runtime.sourceMode || state.sourceMode;
    render();
  } catch (error) {
    renderFatal(`刷新失败：${error.message}`);
  } finally {
    setLoading(false);
  }
}

async function syncFeishu() {
  if (state.sourceMode === 'feishu' || state.runtime?.sourceMode === 'feishu') {
    window.alert('当前数据已来自飞书结果表，无需同步。');
    return;
  }
  const errors = state.runtime?.errors || [];
  if (errors.length) {
    window.alert('当前存在报表计算失败，不能同步飞书。');
    return;
  }
  if (!state.runtime?.reports?.length) {
    window.alert('请先刷新数据，再同步飞书。');
    return;
  }
  const confirmed = window.confirm(syncPreviewText(reports()));
  if (!confirmed) return;
  setLoading(true);
  try {
    const runtime = await fetchJson('/api/sync', { method: 'POST' });
    state.runtime = runtime;
    state.status = await fetchJson('/api/status');
    render();
  } catch (error) {
    renderFatal(`飞书同步失败：${error.message}`);
  } finally {
    setLoading(false);
  }
}

function renderFatal(message) {
  els.noticeBand.textContent = message;
  els.noticeBand.className = 'status-banner error';
}

function reports() {
  return state.runtime?.reports || [];
}

function activeReport() {
  return reports().find((report) => report.id === state.activeReport);
}

function activeError() {
  return (state.runtime?.errors || []).find((error) => error.id === state.activeReport);
}

function parseDate(value) {
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time) : null;
}

function toIsoDate(date) {
  if (!date) return '';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function latestEndDate(report, dimension = state.compareDimension) {
  const dates = (report?.rows || [])
    .filter((row) => !dimension || row['周期类型'] === dimension)
    .map((row) => parseDate(row['结束日期']))
    .filter(Boolean)
    .sort((a, b) => a - b);
  return dates.length ? dates[dates.length - 1] : null;
}

function selectedDateRange(report) {
  if (state.range === 'all') {
    return { start: null, end: null };
  }
  if (state.range === 'custom') {
    return {
      start: parseDate(state.customStart),
      end: parseDate(state.customEnd),
    };
  }
  const end = latestEndDate(report, null);
  if (!end) return { start: null, end: null };
  const start = new Date(end);
  start.setDate(start.getDate() - Number(state.range) + 1);
  return { start, end };
}

function rowInRange(row, range) {
  const end = parseDate(row['结束日期']);
  if (!end) return false;
  if (range.start && end < range.start) return false;
  if (range.end && end > range.end) return false;
  return true;
}

  function rowsFor(report, { dimension = state.compareDimension, rangeFilter = true } = {}) {
    const range = selectedDateRange(report);
    return (report?.rows || []).filter((row) => {
      const dimensionMatch = !dimension || row['周期类型'] === dimension;
      const dateMatch = !rangeFilter || rowInRange(row, range);
      return dimensionMatch && dateMatch;
    });
  }

function rowsForExplicitRange(report, range, dimension = state.compareDimension) {
  return (report?.rows || []).filter((row) => (
      (!dimension || row['周期类型'] === dimension)
      && rowInRange(row, range)
    ));
  }

function displayRowsFor(report) {
  return rowsFor(report).slice().sort((left, right) => {
    const leftTime = parseDate(left['结束日期'] || left['开始日期'])?.getTime() ?? Number.NEGATIVE_INFINITY;
    const rightTime = parseDate(right['结束日期'] || right['开始日期'])?.getTime() ?? Number.NEGATIVE_INFINITY;
    return rightTime - leftTime;
  });
}

function dateRangeFromRows(rows) {
  const dates = rows.map((row) => parseDate(row['结束日期'])).filter(Boolean).sort((a, b) => a - b);
  if (!dates.length) return null;
  return { start: dates[0], end: dates[dates.length - 1] };
}

function displayDateRangeFromRows(rows) {
  const starts = rows.map((row) => parseDate(row['开始日期'] || row['结束日期'])).filter(Boolean).sort((a, b) => a - b);
  const ends = rows.map((row) => parseDate(row['结束日期'] || row['开始日期'])).filter(Boolean).sort((a, b) => a - b);
  if (!starts.length || !ends.length) return null;
  return { start: starts[0], end: ends[ends.length - 1] };
}

function renderKpiPeriod(rows) {
  if (!els.kpiPeriod) return;
  const range = displayDateRangeFromRows(rows);
  const periodText = range ? `${toIsoDate(range.start)} 至 ${toIsoDate(range.end)}` : '当前筛选下无可统计周期';
  els.kpiPeriod.textContent = `当前指标统计周期：${state.compareDimension} · ${periodText}`;
}

function formatNumber(value) {
  const number = Number(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : value || '-';
}

function percentToNumber(value) {
  const text = String(value ?? '').replace('%', '').trim();
  if (!text) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number / 100 : null;
}

function ratioText(value) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value * 100).toFixed(2)}%`;
}

function ppText(value) {
  if (value == null || !Number.isFinite(value)) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}pp`;
}

function trendClass(value) {
  if (value == null || !Number.isFinite(value) || value === 0) return 'neutral';
  return value > 0 ? 'positive' : 'negative';
}

function sumField(rows, field) {
  return rows.reduce((sum, row) => sum + (Number(row[field]) || 0), 0);
}

function aggregateRatio(rows, numeratorField, denominatorField) {
  const numerator = sumField(rows, numeratorField);
  const denominator = sumField(rows, denominatorField);
  return {
    numerator,
    denominator,
    ratio: denominator ? numerator / denominator : null,
  };
}

function aggregatePrivateRatio(rows) {
  const newFriends = sumField(rows, '新加好友');
  const activeTotalFriends = sumField(rows, '活跃累计好友');
  const activeAccounts = sumField(rows, '活跃账号');
  const numerator = activeTotalFriends - newFriends;
  const denominator = activeAccounts - newFriends;
  return {
    numerator,
    denominator,
    ratio: denominator ? numerator / denominator : null,
  };
}

function addDays(date, days) {
  if (!date) return null;
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function addMonths(date, months) {
  if (!date) return null;
  const targetMonth = date.getMonth() + months;
  const lastDay = new Date(date.getFullYear(), targetMonth + 1, 0).getDate();
  return new Date(date.getFullYear(), targetMonth, Math.min(date.getDate(), lastDay));
}

function previousCalendarMonth(date) {
  if (!date) return null;
  return new Date(date.getFullYear(), date.getMonth() - 1, 1);
}

function shiftRangeDays(range, days) {
  if (!range.start || !range.end) return null;
  return {
    start: addDays(range.start, days),
    end: addDays(range.end, days),
  };
}

function previousMonthLabel() {
  return '上月';
}

function monthPeriodRows(report) {
  return (report?.rows || [])
    .filter((row) => row['周期类型'] === '月')
    .slice()
    .sort((a, b) => (parseDate(a['结束日期']) || 0) - (parseDate(b['结束日期']) || 0));
}

function previousMonthReferenceRows(report, currentRows) {
  const currentRange = comparisonDateRange(report, currentRows);
  if (!currentRange?.start) return [];
  const previousMonth = previousCalendarMonth(currentRange.start);
  return monthPeriodRows(report).filter((row) => {
    const rowStart = parseDate(row['开始日期'] || row['结束日期']);
    return rowStart
      && rowStart.getFullYear() === previousMonth.getFullYear()
      && rowStart.getMonth() === previousMonth.getMonth();
  });
}

function monthPeriodLabel(rows) {
  const labels = [...new Set(rows.map((row) => row['统计周期']).filter(Boolean))];
  if (!labels.length) return '';
  return labels.length === 1 ? labels[0] : `${labels[0]}-${labels[labels.length - 1]}`;
}

function rangeLabel(range) {
  if (!range?.start || !range?.end) return '';
  const start = `${range.start.getMonth() + 1}.${String(range.start.getDate()).padStart(2, '0')}`;
  const end = `${range.end.getMonth() + 1}.${String(range.end.getDate()).padStart(2, '0')}`;
  return start === end ? start : `${start}-${end}`;
}

function aggregateForReport(report, rows) {
  if (report.id === 'private') {
    return aggregatePrivateRatio(rows);
  }
  return aggregateRatio(rows, report.numeratorField, report.denominatorField);
}

function comparisonDateRange(report, currentRows) {
  if (state.range === 'all') {
    return null;
  }
  const selectedRange = selectedDateRange(report);
  if (selectedRange?.start && selectedRange?.end) {
    return selectedRange;
  }
  return displayDateRangeFromRows(currentRows) || dateRangeFromRows(currentRows);
}

function rangeShiftChange(report, currentRows, shiftRange) {
  const currentRange = comparisonDateRange(report, currentRows);
  const previousRange = currentRange ? shiftRange(currentRange) : null;
  const previousRows = previousRange ? rowsForExplicitRange(report, previousRange) : [];
  const currentRatio = aggregateForReport(report, currentRows).ratio;
  const previousRatio = aggregateForReport(report, previousRows).ratio;
  return {
    change: currentRatio != null && previousRatio != null ? currentRatio - previousRatio : null,
    previousRatio,
    previousLabel: rangeLabel(previousRange),
  };
}

function unsupportedComparison(message) {
  return {
    change: null,
    previousRatio: null,
    previousLabel: '',
    unsupported: message,
  };
}

function previousMonthChange(report, currentRows) {
  const previousRows = previousMonthReferenceRows(report, currentRows);
  const previousRange = displayDateRangeFromRows(previousRows) || dateRangeFromRows(previousRows);
  const currentRatio = aggregateForReport(report, currentRows).ratio;
  const previousRatio = aggregateForReport(report, previousRows).ratio;
  return {
    change: currentRatio != null && previousRatio != null ? currentRatio - previousRatio : null,
    previousRatio,
    previousLabel: monthPeriodLabel(previousRows) || rangeLabel(previousRange),
  };
}

function rowRatioForReport(report, row) {
  const ratio = percentToNumber(row[report.ratioField]);
  return ratio == null ? aggregateForReport(report, [row]).ratio : ratio;
}

function periodLabelForRow(row) {
  if (!row) return '';
  const range = displayDateRangeFromRows([row]);
  return row['统计周期'] || rangeLabel(range) || '-';
}

function ratioExtremeCards(report, rows) {
  const values = rows
    .map((row) => ({ row, ratio: rowRatioForReport(report, row) }))
    .filter((item) => item.ratio != null && Number.isFinite(item.ratio));
  if (!values.length) {
    return [
      { label: '最高周期', value: '-', hint: '当前筛选下无可统计周期' },
      { label: '最低周期', value: '-', hint: '当前筛选下无可统计周期' },
    ];
  }
  values.sort((left, right) => right.ratio - left.ratio);
  const highest = values[0];
  const lowest = values[values.length - 1];
  return [
    { label: '最高周期', value: ratioText(highest.ratio), hint: periodLabelForRow(highest.row) },
    { label: '最低周期', value: ratioText(lowest.ratio), hint: periodLabelForRow(lowest.row) },
  ];
}

function comparisonCards(report, rows) {
  if (state.compareDimension === '日') {
    return [];
  }
  const cards = [];
  if (state.compareDimension === '周') {
    const week = rangeShiftChange(report, rows, (range) => shiftRangeDays(range, -7));
    cards.push({
      label: '较上周变化',
      value: ppText(week.change),
      hint: ratioCompareHint('上周', week),
      tone: trendClass(week.change),
    });
  }
  const month = previousMonthChange(report, rows);
  cards.push({
    label: '较上月变化',
    value: ppText(month.change),
    hint: ratioCompareHint(previousMonthLabel(), month),
    tone: trendClass(month.change),
  });
  return cards;
}

function ratioCompareHint(label, comparison) {
  if (comparison.unsupported) {
    return comparison.unsupported;
  }
  if (state.range === 'all') {
    return '全部范围不支持环比';
  }
  return comparison.previousLabel ? `${label} ${comparison.previousLabel}：${ratioText(comparison.previousRatio)}` : `无${label}数据`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function render() {
  const report = activeReport();
  renderNavigation();
  renderStatus();
  renderRuntimeInfo();
  renderReportStats();
  renderSources();
  renderSync();
  renderMessages();
  renderSidePanelState();

  if (!report) {
    renderEmptyReport(activeError());
    return;
  }

  els.reportTitle.textContent = report.title;
  els.reportFormula.textContent = '';
  els.lastRefresh.textContent = state.runtime?.generatedAt ? `最后刷新：${state.runtime.generatedAt}` : '';
  renderFilterState(report);
  renderKpis(report);
  renderChart(report);
  renderTable(report);
}

function renderSidePanelState() {
  document.body.classList.toggle('side-panel-collapsed', state.sidePanelCollapsed);
  els.sidePanelButton.setAttribute('aria-label', state.sidePanelCollapsed ? '显示右侧信息' : '隐藏右侧信息');
  els.sidePanelButton.setAttribute('aria-pressed', String(state.sidePanelCollapsed));
}

function renderNavigation() {
  document.querySelectorAll('.nav-button').forEach((button) => {
    button.classList.toggle('active', button.dataset.report === state.activeReport);
    const hasError = (state.runtime?.errors || []).some((error) => error.id === button.dataset.report);
    button.classList.toggle('has-error', hasError);
  });
}

function renderStatus() {
  els.sourceModeTabs?.querySelectorAll('button').forEach((button) => {
    button.classList.toggle('active', button.dataset.sourceMode === state.sourceMode);
  });
    els.dataDir.textContent = state.sourceMode === 'feishu' ? '飞书结果表' : state.status?.dataDir || '未读取';
  const sync = state.runtime?.sync;
  const errors = state.runtime?.errors || [];
  if (!state.runtime?.generatedAt) {
    const text = state.sourceMode === 'feishu' ? '点击“刷新数据”后读取飞书结果表。' : '点击“刷新数据”后读取 data 目录并计算报表。';
    els.noticeBand.textContent = text;
    els.noticeBand.className = 'status-banner neutral';
  } else if (errors.length) {
    const text = state.sourceMode === 'feishu' ? '飞书结果表读取失败，请检查配置、权限和字段。' : '存在报表计算失败，请检查源文件后重新刷新。';
    els.noticeBand.textContent = text;
    els.noticeBand.className = 'status-banner error';
  } else if (state.sourceMode === 'feishu') {
    els.noticeBand.textContent = '飞书结果表当前数据已来自飞书结果表，无需同步。';
    els.noticeBand.className = 'status-banner neutral';
  } else if (sync?.ok) {
    els.noticeBand.textContent = `飞书同步成功：${sync.syncedAt || ''}`;
    els.noticeBand.className = 'status-banner success';
  } else if (sync?.ready) {
    els.noticeBand.textContent = '检查结果无误后，点击“确认同步飞书”。';
    els.noticeBand.className = 'status-banner neutral';
  } else {
    els.noticeBand.textContent = sync?.message || '未知错误';
    els.noticeBand.className = 'status-banner error';
  }
  els.syncButton.disabled = state.loading || state.sourceMode === 'feishu' || errors.length || !reports().length;
}

function periodCounts(rows) {
  const counts = { 日: 0, 周: 0, 月: 0 };
  for (const row of rows || []) {
    const periodType = String(row['周期类型'] || '');
    if (Object.prototype.hasOwnProperty.call(counts, periodType)) counts[periodType] += 1;
  }
  return counts;
}

function periodCountText(counts) {
  return `日 ${counts['日'] || 0} / 周 ${counts['周'] || 0} / 月 ${counts['月'] || 0}`;
}

function syncPreviewItems(targetReports = reports()) {
  return (targetReports || []).map((item) => {
    const rows = item.rows || [];
    const counts = periodCounts(rows);
    const title = item.title || item.id || '报表';
    return {
      title,
      totalRows: rows.length,
      counts,
      summary: `${title}：共 ${rows.length} 行（${periodCountText(counts)}）`,
    };
  });
}

function syncPreviewText(targetReports = reports()) {
  const items = syncPreviewItems(targetReports);
  const totalRows = items.reduce((sum, item) => sum + item.totalRows, 0);
  const lines = [
    `预计同步 ${totalRows} 行，包含日/周/月记录。`,
    ...items.map((item) => item.summary),
    '确认继续同步到飞书？',
  ];
  return lines.join('\n');
}

function renderRuntimeInfo() {
  if (!els.runtimeInfo) return;
  const status = state.status || {};
  const rows = [
    ['后端启动', status.serverStartedAt || '-'],
    ['最后刷新', state.runtime?.generatedAt || status.lastRefresh || '-'],
  ];
  els.runtimeInfo.innerHTML = rows.map(([key, value]) => `
    <dt>${escapeHtml(key)}</dt>
    <dd>${escapeHtml(value)}</dd>
  `).join('');
}

function renderReportStats() {
  if (!els.reportStats) return;
  const items = syncPreviewItems(reports());
  els.reportStats.innerHTML = items.length ? items.map((item) => `
    <article class="source-row">
      <div class="file-badge">#</div>
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <span>共 ${escapeHtml(item.totalRows)} 行 · ${escapeHtml(periodCountText(item.counts))}</span>
      </div>
    </article>
  `).join('') : '<div class="empty small">刷新后显示日/周/月行数</div>';
}

function renderKpis(report) {
  const rows = rowsFor(report);
  renderKpiPeriod(rows);
  let items;
  if (report.id === 'conversion') {
    const aggregate = aggregateRatio(rows, '新增客户数_SCRM', '新登账号_GDATA');
    items = [
      { label: '新登账号数', value: formatNumber(aggregate.denominator), hint: '' },
      { label: '新增客户数', value: formatNumber(aggregate.numerator), hint: '' },
      { label: '新用户转化率', value: ratioText(aggregate.ratio), hint: '新增客户数 / 新登账号数' },
      ...ratioExtremeCards(report, rows),
      ...comparisonCards(report, rows),
      { label: '目标转化率', value: '20.00%', hint: '目标线' },
    ];
  } else {
    const aggregate = aggregatePrivateRatio(rows);
    items = [
      { label: '活跃账号', value: formatNumber(sumField(rows, '活跃账号')), hint: '当前筛选范围总计' },
      { label: '活跃累计好友', value: formatNumber(sumField(rows, '活跃累计好友')), hint: '当前筛选范围总计' },
      { label: '私域占比', value: ratioText(aggregate.ratio), hint: `(${formatNumber(sumField(rows, '活跃累计好友'))} - ${formatNumber(sumField(rows, '新加好友'))}) / (${formatNumber(sumField(rows, '活跃账号'))} - ${formatNumber(sumField(rows, '新加好友'))})` },
      ...ratioExtremeCards(report, rows),
      ...comparisonCards(report, rows),
      { label: '目标私域占比', value: '45.00%', hint: '目标线' },
    ];
  }
  els.kpiGrid.innerHTML = items.map((item) => `
    <article class="kpi">
      <span>${escapeHtml(item.label)}</span>
      <strong class="${escapeHtml(item.tone || '')}">${escapeHtml(item.value)}</strong>
      ${item.hint ? `<small>${escapeHtml(item.hint)}</small>` : ''}
    </article>
  `).join('');
}

function renderChart(report) {
  const rows = rowsFor(report)
    .sort((a, b) => new Date(a['结束日期']) - new Date(b['结束日期']));

  els.denominatorLegend.textContent = report.id === 'conversion' ? '新登账号数' : report.denominatorField;
  els.numeratorLegend.textContent = report.id === 'conversion' ? '新增客户数' : report.numeratorField;
  els.chartSubtitle.textContent = rows.length ? `按${state.compareDimension}展示当前筛选范围内 ${rows.length} 个周期` : `当前筛选下无${state.compareDimension}数据`;

  if (!rows.length) {
    els.chart.innerHTML = '<div class="empty">没有可绘制的数据</div>';
    return;
  }

  const height = 320;
  const padding = { top: 28, right: 58, bottom: 54, left: 72 };
  const width = Math.max(960, padding.left + padding.right + rows.length * 92);
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(...rows.flatMap((row) => [
    Number(row[report.denominatorField]) || 0,
    Number(row[report.numeratorField]) || 0,
  ]), 1);
  const targetRatio = report.id === 'conversion' ? 0.2 : (report.id === 'private' ? 0.45 : null);
  const maxRatio = Math.max(...rows.map((row) => percentToNumber(row[report.ratioField]) || 0), targetRatio || 0, 0.01);
  const band = innerWidth / rows.length;
  const barWidth = Math.min(28, band / 4);
  const x = (index) => padding.left + index * band + band / 2;
  const y = (value) => padding.top + innerHeight - (value / maxValue) * innerHeight;
  const ry = (value) => padding.top + innerHeight - (value / maxRatio) * innerHeight;
  const points = rows.map((row, index) => `${x(index)},${ry(percentToNumber(row[report.ratioField]) || 0)}`).join(' ');
  const grid = [0, 0.25, 0.5, 0.75, 1].map((tick) => {
    const gy = padding.top + innerHeight * tick;
    const label = Math.round(maxValue * (1 - tick)).toLocaleString('zh-CN');
    return `<line x1="${padding.left}" y1="${gy}" x2="${width - padding.right}" y2="${gy}" class="grid-line" />
      <text x="${padding.left - 12}" y="${gy + 4}" text-anchor="end" class="axis-label">${label}</text>`;
  }).join('');
    const bars = rows.map((row, index) => {
      const cx = x(index);
      const denominator = Number(row[report.denominatorField]) || 0;
      const numerator = Number(row[report.numeratorField]) || 0;
      const ratio = percentToNumber(row[report.ratioField]) || 0;
      return `
        <rect x="${cx - barWidth - 3}" y="${y(denominator)}" width="${barWidth}" height="${padding.top + innerHeight - y(denominator)}" rx="3" class="bar blue" />
        <rect x="${cx + 3}" y="${y(numerator)}" width="${barWidth}" height="${padding.top + innerHeight - y(numerator)}" rx="3" class="bar teal" />
        <circle cx="${cx}" cy="${ry(ratio)}" r="4" class="ratio-dot" />
        <text x="${cx}" y="${ry(ratio) - 10}" text-anchor="middle" class="ratio-label">${escapeHtml(row[report.ratioField])}</text>
        <text x="${cx}" y="${height - 20}" text-anchor="middle" class="axis-label">${escapeHtml(row['统计周期'])}</text>`;
    }).join('');
  const targetLine = targetRatio == null ? '' : `
    <line x1="${padding.left}" y1="${ry(targetRatio)}" x2="${width - padding.right}" y2="${ry(targetRatio)}" class="target-line" />
    <text x="${width - padding.right}" y="${ry(targetRatio) - 6}" text-anchor="end" class="target-label">目标 ${ratioText(targetRatio)}</text>`;

  els.chart.innerHTML = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
    ${grid}
    <line x1="${padding.left}" y1="${padding.top + innerHeight}" x2="${width - padding.right}" y2="${padding.top + innerHeight}" class="axis-line" />
    ${targetLine}
    ${bars}
    <polyline points="${points}" class="ratio-line" />
  </svg>`;
}

function renderTable(report) {
  const rows = displayRowsFor(report);
  const columns = rows[0] ? Object.keys(rows[0]) : [];
  els.rowCount.textContent = `${rows.length} 条`;
  els.tableHead.innerHTML = columns.length ? `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr>` : '';
  els.tableBody.innerHTML = rows.map((row) => `
    <tr>${columns.map((column) => `<td>${escapeHtml(row[column] ?? '')}</td>`).join('')}</tr>
  `).join('');
}

function exportCurrentReport() {
  const report = activeReport();
  if (!report) {
    window.alert('没有可导出的报表，请先刷新数据。');
    return;
  }
  const rows = displayRowsFor(report);
  const columns = rows[0] ? Object.keys(rows[0]) : [];
  if (!columns.length) {
    window.alert('当前筛选下没有可导出的数据。');
    return;
  }
  const filename = nextExportFilename(report.title || 'report', 'csv');
  downloadText(filename, csvText(columns, rows), 'text/csv;charset=utf-8');
}

function renderFilterState(report) {
  const range = selectedDateRange(report);
  if (state.range !== 'custom' && range.start && range.end) {
    state.customStart = toIsoDate(range.start);
    state.customEnd = toIsoDate(range.end);
  }
  els.startDateInput.value = state.customStart || '';
  els.endDateInput.value = state.customEnd || '';
  els.customRange.classList.toggle('hidden', state.range !== 'custom');
}

function renderSources() {
  const sources = state.sourceMode === 'feishu'
    ? (activeReport()?.sources || [])
    : (state.status?.sources || []);
  els.sourceList.innerHTML = sources.length ? sources.map((source) => `
    <article class="source-row">
      <div class="file-badge">${source.name.endsWith('.xlsx') ? 'X' : 'C'}</div>
      <div>
        <strong title="${escapeHtml(source.path)}">${escapeHtml(source.name)}</strong>
        <span>${escapeHtml(source.role)} · ${escapeHtml(source.updatedAt)}</span>
      </div>
    </article>
  `).join('') : '<div class="empty small">data 目录下没有源文件</div>';
}

function renderSync() {
  const config = state.status?.config || {};
  const sync = state.runtime?.sync || {};
  const rows = [
    ['数据源', state.sourceMode === 'feishu' ? '飞书结果表' : '本地文件'],
    ['配置', config.configured ? '可用' : (config.error || '不可用')],
    ['飞书状态', feishuStatusText(sync)],
    ['新增', sync.created ?? '-'],
    ['更新', sync.updated ?? '-'],
  ];
  renderFeishuLinks(config.feishuLinks || []).forEach((row) => rows.push(row));
  els.syncInfo.innerHTML = rows.map(([key, value]) => `
    <dt>${escapeHtml(key)}</dt>
    <dd>${String(value).startsWith('<a ') ? value : escapeHtml(value)}</dd>
  `).join('');
}

function feishuStatusText(sync) {
  if (sync.ok) return '成功';
  if (sync.ready) return '等待确认';
  if (sync.blocked) return sync.message || '已阻断';
  return sync.message || '尚未同步';
}

function renderFeishuLinks(links) {
  const items = links.length ? links : [{ label: '飞书结果表', url: '' }];
  return items.map((item) => {
    const label = normalizeFeishuLinkLabel(item.label);
    const url = item.url || '';
    const value = url
      ? `<a class="sync-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">打开</a>`
      : '<span class="sync-link disabled" title="未配置飞书链接">打开</span>';
    return [label, value];
  });
}

function normalizeFeishuLinkLabel(label) {
  if (!label || label === '飞书结果表') return '飞书链接';
  return label.replace(/^飞书结果表/, '飞书链接');
}

function renderMessages() {
  const errors = state.runtime?.errors || [];
  const sync = state.runtime?.sync;
  const messages = [];
  errors.forEach((error) => messages.push({ type: 'error', title: error.title, body: error.body }));
  if (!state.runtime?.generatedAt) {
    messages.push({ type: 'neutral', title: '尚未刷新', body: state.sourceMode === 'feishu' ? '点击“刷新数据”后会从飞书结果表读取数据。' : '点击“刷新数据”后会显示计算结果。确认无误后可同步飞书。' });
  } else if (state.sourceMode === 'feishu') {
    messages.push({ type: 'neutral', title: '飞书结果表模式', body: '当前数据来自飞书结果表，同步按钮已停用。' });
  } else if (sync?.ready) {
    messages.push({ type: 'neutral', title: '等待确认同步', body: '报表已生成本地 CSV，尚未写入飞书。' });
  } else if (sync && !sync.ok && sync.message) {
    messages.push({ type: sync.blocked ? 'warning' : 'error', title: sync.blocked ? '飞书同步已阻断' : '飞书同步失败', body: sync.message });
  }
  if (!messages.length) {
    messages.push({ type: 'success', title: '当前无错误', body: '源文件、计算和同步状态会在刷新后更新。' });
  }
  els.messageList.innerHTML = messages.map((item) => `
    <div class="message ${item.type}">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.body)}</p>
    </div>
  `).join('');
}

function renderEmptyReport(error) {
  els.reportTitle.textContent = error?.title || '没有可展示的报表';
  els.reportFormula.textContent = error?.body || '请先刷新数据。';
  els.lastRefresh.textContent = state.runtime?.generatedAt ? `最后刷新：${state.runtime.generatedAt}` : '';
  els.kpiGrid.innerHTML = '';
  if (els.kpiPeriod) els.kpiPeriod.textContent = '';
  els.chartSubtitle.textContent = '';
  els.chart.innerHTML = `<div class="empty">${escapeHtml(error?.body || '请先刷新数据')}</div>`;
  els.tableHead.innerHTML = '';
  els.tableBody.innerHTML = '';
  els.rowCount.textContent = '0 条';
}

document.querySelectorAll('.nav-button').forEach((button) => {
  button.addEventListener('click', () => {
    state.activeReport = button.dataset.report;
    document.querySelectorAll('.nav-button').forEach((item) => item.classList.toggle('active', item === button));
    render();
  });
});

els.rangeTabs.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-range]');
  if (!button) return;
  state.range = button.dataset.range;
  els.rangeTabs.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
  render();
});

els.compareTabs.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-dimension]');
  if (!button) return;
  state.compareDimension = button.dataset.dimension;
  els.compareTabs.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
  render();
});

  els.sourceModeTabs.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-source-mode]');
    if (!button) return;
    state.sourceMode = button.dataset.sourceMode;
  els.sourceModeTabs.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
  render();
});

els.startDateInput.addEventListener('change', (event) => {
  state.customStart = event.target.value;
  render();
});

els.endDateInput.addEventListener('change', (event) => {
  state.customEnd = event.target.value;
  render();
});

  els.refreshButton.addEventListener('click', refreshReports);
els.syncButton.addEventListener('click', syncFeishu);
els.exportButton.addEventListener('click', exportCurrentReport);
els.menuButton.addEventListener('click', () => {
  document.body.classList.toggle('nav-collapsed');
});

els.sidePanelButton.addEventListener('click', () => {
  state.sidePanelCollapsed = !state.sidePanelCollapsed;
  localStorage.setItem('gdataSidePanelCollapsed', String(state.sidePanelCollapsed));
  renderSidePanelState();
});


  loadInitial();
}
