const state = {
  status: null,
  runtime: null,
  activeReport: 'daily',
  range: 'all',
  period: '日',
    metric: '次留',
    dataSource: 'feishu',
    customStart: '',
    customEnd: '',
    loading: false,
  sidePanelCollapsed: localStorage.getItem('retention30SidePanelCollapsed') !== 'false',
};

const CAMPAIGN_START_DATE = '2026-05-26';

const els = {
  dataDir: document.querySelector('#dataDir'),
  refreshButton: document.querySelector('#refreshButton'),
  syncButton: document.querySelector('#syncButton'),
  exportButton: document.querySelector('#exportButton'),
  menuButton: document.querySelector('#menuButton'),
  sidePanelButton: document.querySelector('#sidePanelButton'),
  rangeTabs: document.querySelector('#rangeTabs'),
  periodTabs: document.querySelector('#periodTabs'),
  periodFilter: document.querySelector('#periodFilter'),
  metricTabs: document.querySelector('#metricTabs'),
    customRange: document.querySelector('#customRange'),
    startDateInput: document.querySelector('#startDateInput'),
    endDateInput: document.querySelector('#endDateInput'),
    sourceModeTabs: document.querySelector('#sourceModeTabs'),
  noticeBand: document.querySelector('#noticeBand'),
  reportTitle: document.querySelector('#reportTitle'),
  reportDescription: document.querySelector('#reportDescription'),
  lastRefresh: document.querySelector('#lastRefresh'),
  kpiGrid: document.querySelector('#kpiGrid'),
  kpiPeriod: document.querySelector('#kpiPeriod'),
  chartTitle: document.querySelector('#chartTitle'),
  chartSubtitle: document.querySelector('#chartSubtitle'),
  chartLegend: document.querySelector('#chartLegend'),
  chart: document.querySelector('#chart'),
  rowCount: document.querySelector('#rowCount'),
  tableHead: document.querySelector('#tableHead'),
  tableBody: document.querySelector('#tableBody'),
  sourceList: document.querySelector('#sourceList'),
  syncInfo: document.querySelector('#syncInfo'),
  messageList: document.querySelector('#messageList'),
};

const marketFields = {
  次留: '大盘次留',
  '3日留': '大盘3日留',
  '7日留': '大盘7日留',
};

const CAMPAIGN_COMPARE_DAYS = 30;

function canSyncCurrentLocalResult() {
  return Boolean(state.status?.lastRefresh) && !state.status?.lastSync?.blocked;
}

function setLoading(loading) {
  state.loading = loading;
  els.refreshButton.disabled = loading;
  els.syncButton.disabled = loading || !canSyncCurrentLocalResult();
  els.sourceModeTabs.querySelectorAll('button').forEach((button) => {
    const isLocal = button.dataset.sourceMode === 'local';
    button.disabled = loading;
  });
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
  const key = `retention30-export-${base}.${extension}`;
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
  const bytes = new TextEncoder().encode(text);
  const blob = new Blob([bytes], { type });
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
      fetchJson('/api/reports?source=feishu'),
    ]);
    state.status = status;
    state.runtime = runtime;
    state.dataSource = runtime.dataSource || 'feishu';
    render();
  } catch (error) {
    renderFatal(`页面初始化失败：${error.message}`);
  }
}

async function loadReportsFromSource(source) {
  const dataSource = source;
  state.dataSource = dataSource;
  state.runtime = await fetchJson(`/api/reports?source=${encodeURIComponent(dataSource)}`);
}

async function refreshReports() {
  setLoading(true);
  try {
    const runtime = await fetchJson('/api/refresh', { method: 'POST' });
    state.status = runtime.status;
    if (state.dataSource === 'local') {
      state.runtime = { ...runtime, dataSource: 'local', sourceName: '本地结果文件' };
    } else {
      await loadReportsFromSource(state.dataSource);
    }
    render();
  } catch (error) {
    renderFatal(`刷新失败：${error.message}`);
  } finally {
    setLoading(false);
  }
}

async function syncFeishu() {
  if (!canSyncCurrentLocalResult()) {
    window.alert('请先刷新数据，再同步飞书。');
    return;
  }
  const confirmed = window.confirm('确认将当前 30 日留存结果同步到飞书多维表格？已有记录会更新，汇总表过期自动记录会清理。');
  if (!confirmed) return;
  setLoading(true);
  try {
    await fetchJson('/api/sync', { method: 'POST' });
    state.status = await fetchJson('/api/status');
    await loadReportsFromSource(state.dataSource);
    render();
  } catch (error) {
    renderFatal(`飞书同步失败：${error.message}`);
  } finally {
    setLoading(false);
  }
}

function reports() {
  return state.runtime?.reports || [];
}

function activeReport() {
  return reports().find((report) => report.id === 'daily');
}

function hasBlockingErrors() {
  return Boolean(state.runtime?.errors?.length);
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

function dateValue(report, row) {
  return row['结束日期'] || row['开始日期'];
}

function periodLabel(row) {
  return row['统计周期'] || '';
}

function latestDate(report) {
  const dates = (report?.rows || [])
    .map((row) => parseDate(dateValue(report, row)))
    .filter(Boolean)
    .sort((a, b) => a - b);
  return dates.length ? dates[dates.length - 1] : null;
}

function selectedDateRange(report) {
  if (state.range === 'all') {
    return { start: null, end: null };
  }
  if (state.range === 'campaign') {
    return {
      start: parseDate(CAMPAIGN_START_DATE),
      end: latestDate(report),
    };
  }
  if (state.range === 'custom') {
    return {
      start: parseDate(state.customStart),
      end: parseDate(state.customEnd),
    };
  }
  const end = latestDate(report);
  if (!end) return { start: null, end: null };
  const start = new Date(end);
  start.setDate(start.getDate() - Number(state.range) + 1);
  return { start, end };
}

function rowInRange(report, row, range) {
  const date = parseDate(dateValue(report, row));
  if (!date) return false;
  if (range.start && date < range.start) return false;
  if (range.end && date > range.end) return false;
  return true;
}

function rowsFor(report) {
  const range = selectedDateRange(report);
  return (report?.rows || []).filter((row) => {
    const periodMatch = row['周期类型'] === state.period;
    return periodMatch && rowInRange(report, row, range);
  });
}

function displayRowsFor(report) {
  return rowsFor(report).slice().sort((left, right) => {
    const leftTime = parseDate(dateValue(report, left))?.getTime() ?? Number.NEGATIVE_INFINITY;
    const rightTime = parseDate(dateValue(report, right))?.getTime() ?? Number.NEGATIVE_INFINITY;
    return rightTime - leftTime;
  });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatNumber(value) {
  const number = Number(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : value || '-';
}

function percentToNumber(value) {
  const text = String(value ?? '').replace('%', '').trim();
  if (!text || text === '-') return null;
  const number = Number(text);
  return Number.isFinite(number) ? number / 100 : null;
}

function percentText(value) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value * 100).toFixed(2)}%`;
}

function weightedPercentValue(rows, field) {
  let weightedSum = 0;
  let users = 0;
  rows.forEach((row) => {
    const value = percentToNumber(row[field]);
    if (value == null) return;
    const rowUsers = Number(row['用户数']) || 0;
    weightedSum += rowUsers * value;
    users += rowUsers;
  });
  return users ? weightedSum / users : null;
}

function ppText(value) {
  if (value == null || !Number.isFinite(value)) return '—';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}pp`;
}

function rateDelta(current, previous) {
  return current == null || previous == null ? null : current - previous;
}

function weightedMarketGap(rows, metric) {
  const marketField = marketFields[metric];
  if (!marketField) return null;
  const comparableRows = rows.filter((row) => (
    percentToNumber(row[metric]) != null
    && percentToNumber(row[marketField]) != null
  ));
  const value = weightedPercentValue(comparableRows, metric);
  const marketValue = weightedPercentValue(comparableRows, marketField);
  return value == null || marketValue == null ? null : value - marketValue;
}

function startOfWeek(date) {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  const offset = (result.getDay() + 6) % 7;
  result.setDate(result.getDate() - offset);
  return result;
}

function addDays(date, days) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date, months) {
  const targetMonth = date.getMonth() + months;
  const lastDay = new Date(date.getFullYear(), targetMonth + 1, 0).getDate();
  return new Date(date.getFullYear(), targetMonth, Math.min(date.getDate(), lastDay));
}

function rowsBetween(report, rows, start, end) {
  return rows.filter((row) => {
    const date = parseDate(dateValue(report, row));
    return date && date >= start && date <= end;
  });
}

function comparisonRows(report) {
  const rows = report?.rows || [];
  return rows.filter((row) => row['周期类型'] === state.period);
}

function kpiRows(report, rows) {
  return rows;
}

function rowDateRange(report, rows) {
  const dates = rows.map((row) => parseDate(dateValue(report, row))).filter(Boolean).sort((a, b) => a - b);
  if (!dates.length) return null;
  return { start: dates[0], end: dates[dates.length - 1] };
}

function displayDateRangeFromRows(report, rows) {
  const starts = rows.map((row) => parseDate(row['开始日期'] || row['结束日期'])).filter(Boolean).sort((a, b) => a - b);
  const ends = rows.map((row) => parseDate(row['结束日期'] || row['开始日期'])).filter(Boolean).sort((a, b) => a - b);
  if (!starts.length || !ends.length) return null;
  return { start: starts[0], end: ends[ends.length - 1] };
}

function renderKpiPeriod(report, rows) {
  if (!els.kpiPeriod) return;
  const range = displayDateRangeFromRows(report, rows);
  const dimension = state.period;
  const periodText = range ? `${toIsoDate(range.start)} 至 ${toIsoDate(range.end)}` : '当前筛选下无可统计周期';
  els.kpiPeriod.textContent = `当前指标统计周期：${state.metric} · ${dimension} · ${periodText}`;
}

function shiftedRows(report, rows, range, shiftStart, shiftEnd) {
  if (!range) return [];
  return rowsBetween(report, rows, shiftStart(range.start), shiftEnd(range.end));
}

function comparisonDateRange(report, currentRows) {
  if (state.range === 'all') {
    return null;
  }
  const selectedRange = selectedDateRange(report);
  if (state.range === 'campaign') {
    return displayDateRangeFromRows(report, currentRows) || rowDateRange(report, currentRows) || selectedRange;
  }
  if (selectedRange?.start && selectedRange?.end) {
    return selectedRange;
  }
  return displayDateRangeFromRows(report, currentRows) || rowDateRange(report, currentRows);
}

function shiftedDateRange(range, shiftStart, shiftEnd) {
  if (!range) return null;
  return { start: shiftStart(range.start), end: shiftEnd(range.end) };
}

function campaignControlRange() {
  const campaignStart = parseDate(CAMPAIGN_START_DATE);
  if (!campaignStart) return null;
  return {
    start: new Date(campaignStart.getFullYear(), campaignStart.getMonth() - 1, 1),
    end: addDays(campaignStart, -CAMPAIGN_COMPARE_DAYS),
  };
}

function campaignComparisonRange(report, range, fallbackRange) {
  if (state.range !== 'campaign' || !range?.end || !fallbackRange?.start) {
    return fallbackRange;
  }
  const campaignStart = parseDate(CAMPAIGN_START_DATE);
  if (!campaignStart || fallbackRange.start >= campaignStart) {
    return fallbackRange;
  }
  const daysAfterCampaign = Math.floor((range.end - campaignStart) / 86400000) + 1;
  return daysAfterCampaign >= CAMPAIGN_COMPARE_DAYS * 2 ? fallbackRange : campaignControlRange();
}

function rangeLabel(range) {
  if (!range?.start || !range?.end) return '';
  const start = `${range.start.getMonth() + 1}.${String(range.start.getDate()).padStart(2, '0')}`;
  const end = `${range.end.getMonth() + 1}.${String(range.end.getDate()).padStart(2, '0')}`;
  return start === end ? start : `${start}-${end}`;
}

function metricComparison(report, currentRows, allRows, metric, shiftStart, shiftEnd, options = {}) {
  const range = comparisonDateRange(report, currentRows);
  const shiftedRange = shiftedDateRange(range, shiftStart, shiftEnd);
  const previousRange = options.useCampaignControl
    ? campaignComparisonRange(report, range, shiftedRange)
    : shiftedRange;
  const previousRows = previousRange ? rowsBetween(report, allRows, previousRange.start, previousRange.end) : [];
  const actualPreviousRange = displayDateRangeFromRows(report, previousRows) || rowDateRange(report, previousRows) || previousRange;
  const currentValue = weightedPercentValue(currentRows, metric);
  const previousValue = weightedPercentValue(previousRows, metric);
  return {
    delta: rateDelta(currentValue, previousValue),
    previousValue,
    previousLabel: rangeLabel(actualPreviousRange),
    previousTargetLabel: rangeLabel(previousRange),
  };
}

function marketGapComparison(report, currentRows, allRows, metric, shiftStart, shiftEnd, options = {}) {
  const range = comparisonDateRange(report, currentRows);
  const shiftedRange = shiftedDateRange(range, shiftStart, shiftEnd);
  const previousRange = options.useCampaignControl
    ? campaignComparisonRange(report, range, shiftedRange)
    : shiftedRange;
  const previousRows = previousRange ? rowsBetween(report, allRows, previousRange.start, previousRange.end) : [];
  const actualPreviousRange = displayDateRangeFromRows(report, previousRows) || rowDateRange(report, previousRows) || previousRange;
  const currentValue = weightedMarketGap(currentRows, metric);
  const previousValue = weightedMarketGap(previousRows, metric);
  return {
    delta: rateDelta(currentValue, previousValue),
    previousValue,
    previousLabel: rangeLabel(actualPreviousRange),
    previousTargetLabel: rangeLabel(previousRange),
  };
}

function useNaturalMonthComparison(report) {
  return state.period === '月';
}

function previousMonthShiftStart(report) {
  return useNaturalMonthComparison(report) ? ((date) => addMonths(date, -1)) : ((date) => addDays(date, -30));
}

function previousMonthLabel(report) {
  return '上月';
}

function weeklyMetricDelta(report, currentRows, allRows, metric) {
  return metricComparison(report, currentRows, allRows, metric, (date) => addDays(date, -7), (date) => addDays(date, -7)).delta;
}

function monthlyMetricDelta(report, currentRows, allRows, metric) {
  const shift = previousMonthShiftStart(report);
  return metricComparison(report, currentRows, allRows, metric, shift, shift, { useCampaignControl: true }).delta;
}

function weeklyMarketGapDelta(report, currentRows, allRows, metric) {
  return marketGapComparison(report, currentRows, allRows, metric, (date) => addDays(date, -7), (date) => addDays(date, -7)).delta;
}

function monthlyMarketGapDelta(report, currentRows, allRows, metric) {
  const shift = previousMonthShiftStart(report);
  return marketGapComparison(report, currentRows, allRows, metric, shift, shift, { useCampaignControl: true }).delta;
}

function percentCompareHint(label, comparison) {
  if (comparison.unsupported) {
    return comparison.unsupported;
  }
  if (state.range === 'all') {
    return '全部范围不支持环比';
  }
  if (!comparison.previousLabel) {
    return `无${label}数据`;
  }
  const period = comparison.previousTargetLabel && comparison.previousTargetLabel !== comparison.previousLabel
    ? `${comparison.previousTargetLabel}（实际 ${comparison.previousLabel}）`
    : comparison.previousLabel;
  return `${label} ${period}：${percentText(comparison.previousValue)}`;
}

function trendClass(value) {
  const number = Number(String(value ?? '').replace(/,/g, '').replace('%', '').replace('pp', ''));
  if (!Number.isFinite(number) || number === 0) return 'neutral';
  return number > 0 ? 'positive' : 'negative';
}

function renderFatal(message) {
  els.noticeBand.textContent = message;
  els.noticeBand.className = 'status-banner error';
}

function render() {
  const report = activeReport();
  renderNavigation();
  renderStatus();
  renderSources();
  renderSync();
  renderMessages();
  renderSidePanelState();
  renderFilterState(report);

  if (!report) {
    renderEmptyReport();
    return;
  }

  els.reportTitle.textContent = report.title;
  els.reportDescription.textContent = report.description || '';
  els.lastRefresh.textContent = state.runtime?.generatedAt ? `最后刷新：${state.runtime.generatedAt}` : '';
  renderKpis(report);
  renderChart(report);
  renderTable(report);
}

function renderNavigation() {
  document.querySelectorAll('.nav-button').forEach((button) => {
    button.classList.toggle('active', button.dataset.report === state.activeReport);
    button.classList.toggle('has-error', hasBlockingErrors());
  });
}

function renderSidePanelState() {
  document.body.classList.toggle('side-panel-collapsed', state.sidePanelCollapsed);
  els.sidePanelButton.setAttribute('aria-label', state.sidePanelCollapsed ? '显示右侧信息' : '隐藏右侧信息');
  els.sidePanelButton.setAttribute('aria-pressed', String(state.sidePanelCollapsed));
}

function renderStatus() {
  els.sourceModeTabs.querySelectorAll('button').forEach((button) => {
    button.classList.toggle('active', button.dataset.sourceMode === state.dataSource);
  });
    els.dataDir.textContent = state.dataSource === 'feishu' ? '飞书结果表' : state.status?.dataDir || '未读取';
  const errors = state.runtime?.errors || [];
  const sync = state.runtime?.sync;
  const sourceName = state.runtime?.sourceName || (state.dataSource === 'local' ? '本地结果文件' : '飞书结果表');
  if (!state.runtime?.generatedAt) {
    els.noticeBand.textContent = '点击“刷新数据”后读取 data 目录并生成 30 日留存结果。';
    els.noticeBand.className = 'status-banner neutral';
  } else if (errors.length) {
    els.noticeBand.textContent = errors[0]?.body || '请检查数据来源。';
    els.noticeBand.className = 'status-banner error';
  } else if (state.dataSource === 'feishu' || sync?.sourceMode === 'feishu') {
    els.noticeBand.textContent = '飞书结果表当前数据已来自飞书结果表，无需同步。';
    els.noticeBand.className = 'status-banner neutral';
  } else if (sync?.ok) {
    els.noticeBand.textContent = sync.message || `已读取${sourceName}`;
    els.noticeBand.className = 'status-banner success';
  } else if (sync?.ready) {
    els.noticeBand.textContent = '检查结果无误后，点击“确认同步飞书”。';
    els.noticeBand.className = 'status-banner neutral';
  } else {
    els.noticeBand.textContent = sync?.message || '当前来源结果已加载。';
    els.noticeBand.className = 'status-banner neutral';
  }
  els.syncButton.disabled = state.loading || !canSyncCurrentLocalResult();
}

function renderFilterState(report) {
  els.periodFilter.classList.remove('hidden');
  const range = selectedDateRange(report);
  if (state.range !== 'custom' && range.start && range.end) {
    state.customStart = toIsoDate(range.start);
    state.customEnd = toIsoDate(range.end);
  }
  els.startDateInput.value = state.customStart || '';
  els.endDateInput.value = state.customEnd || '';
  els.customRange.classList.toggle('hidden', state.range !== 'custom');
}

function renderKpis(report) {
  const rows = rowsFor(report);
  const metric = state.metric;
  const compareRows = comparisonRows(report);
  const currentRows = kpiRows(report, rows);
  renderKpiPeriod(report, currentRows);
  const weightedValue = weightedPercentValue(currentRows, metric);
  const marketGap = weightedMarketGap(currentRows, metric);
  const weeklyMetric = state.range === 'campaign'
    ? { delta: null, previousValue: null, previousLabel: '', unsupported: '活动开启后不统计较上周变化' }
    : metricComparison(report, currentRows, compareRows, metric, (date) => addDays(date, -7), (date) => addDays(date, -7));
  const monthShift = previousMonthShiftStart(report);
  const monthLabel = previousMonthLabel(report);
  const monthlyMetric = metricComparison(report, currentRows, compareRows, metric, monthShift, monthShift, { useCampaignControl: true });
  const marketGapWeekly = state.range === 'campaign'
    ? { delta: null, previousValue: null, previousLabel: '', unsupported: '活动开启后不统计较上周变化' }
    : marketGapComparison(report, currentRows, compareRows, metric, (date) => addDays(date, -7), (date) => addDays(date, -7));
  const marketGapMonthly = marketGapComparison(report, currentRows, compareRows, metric, monthShift, monthShift, { useCampaignControl: true });
  const items = [
    {
      label: `加权 ${metric}`,
      value: percentText(weightedValue),
      hint: `当前口径 ${formatNumber(currentRows.length)} 行`,
    },
    {
      label: '较上周变化',
      value: ppText(weeklyMetric.delta),
      hint: percentCompareHint('上周', weeklyMetric),
    },
    {
      label: `较${monthLabel}变化`,
      value: ppText(monthlyMetric.delta),
      hint: percentCompareHint(monthLabel, monthlyMetric),
    },
    {
      label: '较大盘变化',
      value: ppText(marketGap),
      hint: state.range === 'all'
        ? '全部范围不支持环比'
        : state.range === 'campaign'
          ? `较${monthLabel} ${ppText(marketGapMonthly.delta)}`
          : `较上周 ${ppText(marketGapWeekly.delta)} / 较${monthLabel} ${ppText(marketGapMonthly.delta)}`,
    },
  ];
  els.kpiGrid.innerHTML = items.map((item) => `
    <article class="kpi">
      <span>${escapeHtml(item.label)}</span>
      <strong class="${escapeHtml(item.tone || trendClass(item.value))}">${escapeHtml(item.value)}</strong>
      <small>${escapeHtml(item.hint)}</small>
    </article>
  `).join('');
}

function renderChart(report) {
  const rows = rowsFor(report)
    .slice()
    .sort((a, b) => (parseDate(dateValue(report, a)) || 0) - (parseDate(dateValue(report, b)) || 0));
  const metric = state.metric;
  const marketField = marketFields[metric];
  els.chartTitle.textContent = '留存趋势';
  els.chartSubtitle.textContent = rows.length ? `按 ${metric} 展示当前筛选范围内 ${rows.length} 行` : `当前筛选下没有 ${metric} 数据`;
  els.chartLegend.innerHTML = `
    <span><i class="swatch blue"></i><b>用户数</b></span>
    <span><i class="swatch orange"></i><b>${escapeHtml(metric)}</b></span>
    ${marketField ? `<span><i class="swatch gray"></i><b>${escapeHtml(marketField)}</b></span>` : ''}
  `;

  if (!rows.length) {
    els.chart.innerHTML = '<div class="empty">没有可绘制的数据</div>';
    return;
  }

  const height = 320;
  const padding = { top: 28, right: 58, bottom: 54, left: 72 };
  const width = Math.max(960, padding.left + padding.right + rows.length * 86);
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maxUsers = Math.max(...rows.map((row) => Number(row['用户数']) || 0), 1);
  const rateValues = rows.flatMap((row) => [
    percentToNumber(row[metric]),
    marketField ? percentToNumber(row[marketField]) : null,
  ]).filter((value) => value != null);
  const maxRate = Math.max(...rateValues, 0.01);
  const band = innerWidth / rows.length;
  const barWidth = Math.min(30, band / 3);
  const x = (index) => padding.left + index * band + band / 2;
  const yUsers = (value) => padding.top + innerHeight - (value / maxUsers) * innerHeight;
  const yRate = (value) => padding.top + innerHeight - (value / maxRate) * innerHeight;
  const linePoints = rows
    .map((row, index) => {
      const value = percentToNumber(row[metric]);
      return value == null ? '' : `${x(index)},${yRate(value)}`;
    })
    .filter(Boolean)
    .join(' ');
  const marketPoints = rows
    .map((row, index) => {
      const value = marketField ? percentToNumber(row[marketField]) : null;
      return value == null ? '' : `${x(index)},${yRate(value)}`;
    })
    .filter(Boolean)
    .join(' ');
  const grid = [0, 0.25, 0.5, 0.75, 1].map((tick) => {
    const gy = padding.top + innerHeight * tick;
    const label = Math.round(maxUsers * (1 - tick)).toLocaleString('zh-CN');
    return `<line x1="${padding.left}" y1="${gy}" x2="${width - padding.right}" y2="${gy}" class="grid-line" />
      <text x="${padding.left - 12}" y="${gy + 4}" text-anchor="end" class="axis-label">${label}</text>`;
  }).join('');
    const bars = rows.map((row, index) => {
      const cx = x(index);
      const users = Number(row['用户数']) || 0;
      const rate = percentToNumber(row[metric]);
      const marketRate = marketField ? percentToNumber(row[marketField]) : null;
      const label = periodLabel(row);
      return `
        <rect x="${cx - barWidth / 2}" y="${yUsers(users)}" width="${barWidth}" height="${padding.top + innerHeight - yUsers(users)}" rx="3" class="bar blue" />
        <text x="${cx}" y="${yUsers(users) - 6}" text-anchor="middle" class="user-label">${formatNumber(users)}</text>
        ${rate == null ? '' : `<circle cx="${cx}" cy="${yRate(rate)}" r="4" class="rate-dot" />
        <text x="${cx}" y="${yRate(rate) - 10}" text-anchor="middle" class="rate-label">${escapeHtml(row[metric])}</text>`}
        ${marketRate == null ? '' : `<circle cx="${cx}" cy="${yRate(marketRate)}" r="4" class="market-dot" />`}
        <text x="${cx}" y="${height - 20}" text-anchor="middle" class="axis-label">${escapeHtml(label)}</text>`;
    }).join('');

  els.chart.innerHTML = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
    ${grid}
    <line x1="${padding.left}" y1="${padding.top + innerHeight}" x2="${width - padding.right}" y2="${padding.top + innerHeight}" class="axis-line" />
    ${bars}
    ${linePoints ? `<polyline points="${linePoints}" class="rate-line" />` : ''}
    ${marketPoints ? `<polyline points="${marketPoints}" class="market-line" />` : ''}
  </svg>`;
}

function renderTable(report) {
  const rows = displayRowsFor(report);
  const columns = report.fieldnames || (rows[0] ? Object.keys(rows[0]) : []);
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
  const columns = report.fieldnames || [];
  if (!columns.length) {
    window.alert('当前报表没有可导出的字段。');
    return;
  }
  const filename = nextExportFilename('30日留存数据', 'csv');
  downloadText(filename, csvText(columns, report.rows || []), 'text/csv;charset=utf-8');
}

function renderSources() {
  const sources = state.status?.sources || [];
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
    ['数据源', state.dataSource === 'feishu' ? '飞书结果表' : '本地结果文件'],
    ['配置', config.ready ? '可用' : (config.message || '不可用')],
    ['飞书状态', feishuStatusText(sync)],
    ['新增', sync.created ?? sync.createdFields ?? '-'],
    ['更新', sync.updated ?? sync.updatedFields ?? '-'],
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
    messages.push({ type: 'neutral', title: '尚未刷新', body: '点击“刷新数据”后会生成本地 xlsx，确认后才能同步飞书。' });
  } else if (sync?.ready) {
    messages.push({ type: 'neutral', title: '等待确认同步', body: '本地结果已生成，请检查图表和明细后再写入飞书。' });
  } else if (sync && !sync.ok && sync.message) {
    messages.push({ type: sync.blocked ? 'warning' : 'error', title: sync.blocked ? '飞书同步已阻断' : '飞书同步失败', body: sync.message });
  }
  if (!messages.length) {
    messages.push({ type: 'success', title: '当前无错误', body: '源文件、计算结果和同步状态会在刷新后更新。' });
  }
  els.messageList.innerHTML = messages.map((item) => `
    <div class="message ${item.type}">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.body)}</p>
    </div>
  `).join('');
}

function renderEmptyReport() {
  const error = state.runtime?.errors?.[0];
  els.reportTitle.textContent = error?.title || '没有可展示的报表';
  els.reportDescription.textContent = error?.body || '请先刷新数据。';
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

els.periodTabs.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-period]');
  if (!button) return;
  state.period = button.dataset.period;
  els.periodTabs.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
  render();
});

els.metricTabs.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-metric]');
  if (!button) return;
  state.metric = button.dataset.metric;
  els.metricTabs.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
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

    els.sourceModeTabs.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-source-mode]');
    if (!button || button.dataset.sourceMode === state.dataSource) return;
    setLoading(true);
  try {
    await loadReportsFromSource(button.dataset.sourceMode);
    render();
  } catch (error) {
    renderFatal(`读取数据来源失败：${error.message}`);
  } finally {
    setLoading(false);
  }
});

els.refreshButton.addEventListener('click', refreshReports);
els.syncButton.addEventListener('click', syncFeishu);
els.exportButton.addEventListener('click', exportCurrentReport);
els.menuButton.addEventListener('click', () => {
  document.body.classList.toggle('nav-collapsed');
});
els.sidePanelButton.addEventListener('click', () => {
  state.sidePanelCollapsed = !state.sidePanelCollapsed;
  localStorage.setItem('retention30SidePanelCollapsed', String(state.sidePanelCollapsed));
  renderSidePanelState();
});

loadInitial();
