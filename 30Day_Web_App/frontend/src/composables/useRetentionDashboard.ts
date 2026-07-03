// 30 日留存看板状态控制器：承接数据加载、筛选、图表、导出和同步交互。

import { computed, onMounted, reactive, ref, watchEffect } from 'vue'

import { fetchReports, fetchStatus, refreshReports as requestRefreshReports, syncReports as requestSyncReports } from '@/service/api'
import type { Report, ReportRow, ReportSource, RuntimePayload, StatusPayload } from '@/types/report'
import { csvText, exportTimestamp, safeFilePart } from '@/utils/csv'
import {
  addDays,
  addMonths,
  dateValue,
  displayDateRangeFromRows,
  displayRowsFor,
  marketFields,
  parseDate,
  percentToNumber,
  periodLabel,
  rangeLabel,
  rowsFor,
  selectedDateRange,
  toIsoDate,
  weightedMarketGap,
  weightedPercentValue,
  type DateRange,
} from '@/utils/report'

const CAMPAIGN_START_DATE = '2026-05-26'
const CAMPAIGN_COMPARE_DAYS = 30

type RangeType = 'all' | 'campaign' | 'custom' | '7' | '30'
type PeriodType = '日' | '周' | '月'

type SyncPayload = Record<string, unknown>

interface SourceItem {
  name?: string
  path?: string
  role?: string
  updatedAt?: string
}

interface MessageItem {
  type: 'success' | 'neutral' | 'warning' | 'error'
  title: string
  body: string
}

interface KpiItem {
  label: string
  value: string
  hint: string
  tone: string
}

interface ComparisonResult {
  delta: number | null
  previousValue: number | null
  previousLabel: string
  previousTargetLabel: string
  unsupported?: string
}

interface SyncRow {
  key: string
  value?: string
  url?: string
  disabled?: boolean
}

export function useRetentionDashboard() {
  const status = ref<StatusPayload | null>(null)
  const runtime = ref<RuntimePayload | null>(null)
  const fatalMessage = ref('')
  const loading = ref(false)
  const navCollapsed = ref(false)
  const sidePanelCollapsed = ref(localStorage.getItem('retention30SidePanelCollapsed') !== 'false')
  const filters = reactive({
    activeReport: 'daily',
    range: 'all' as RangeType,
    period: '日' as PeriodType,
    metric: '次留',
    dataSource: 'feishu' as ReportSource,
    customStart: '',
    customEnd: '',
  })

  const reportFilters = computed(() => ({
    range: filters.range,
    period: filters.period,
    customStart: filters.customStart,
    customEnd: filters.customEnd,
    campaignStartDate: CAMPAIGN_START_DATE,
  }))

  const reports = computed(() => runtime.value?.reports || [])
  const activeReport = computed(() => reports.value.find((report) => report.id === filters.activeReport))
  const hasBlockingErrors = computed(() => Boolean(runtime.value?.errors?.length))
  const currentRows = computed(() => (activeReport.value ? rowsFor(activeReport.value, reportFilters.value) : []))
  const sortedRows = computed(() => (activeReport.value ? displayRowsFor(activeReport.value, reportFilters.value) : []))
  const tableColumns = computed(() => activeReport.value?.fieldnames || (sortedRows.value[0] ? Object.keys(sortedRows.value[0]) : []))

  const reportTitle = computed(() => {
    if (activeReport.value) return activeReport.value.title
    return runtime.value?.errors?.[0]?.title || '没有可展示的报表'
  })
  const reportDescription = computed(() => {
    if (activeReport.value) return activeReport.value.description || ''
    return runtime.value?.errors?.[0]?.body || '请先刷新数据。'
  })
  const lastRefreshText = computed(() => (runtime.value?.generatedAt ? `最后刷新：${runtime.value.generatedAt}` : ''))
  const dataDirText = computed(() => (filters.dataSource === 'feishu' ? '飞书结果表' : status.value?.dataDir || '未读取'))
  const canSyncCurrentLocalResult = computed(() => Boolean(status.value?.lastRefresh) && !Boolean(status.value?.lastSync?.blocked))
  const syncButtonDisabled = computed(() => loading.value || !canSyncCurrentLocalResult.value)

  const notice = computed(() => {
    if (fatalMessage.value) return { text: fatalMessage.value, className: 'status-banner error' }
    const errors = runtime.value?.errors || []
    const sync = runtime.value?.sync as SyncPayload | undefined
    const sourceName = runtime.value?.sourceName || (filters.dataSource === 'local' ? '本地结果文件' : '飞书结果表')
    if (!runtime.value?.generatedAt) {
      return { text: '点击“刷新数据”后读取 data 目录并生成 30 日留存结果。', className: 'status-banner neutral' }
    }
    if (errors.length) {
      return { text: errors[0]?.body || '请检查数据来源。', className: 'status-banner error' }
    }
    if (filters.dataSource === 'feishu' || sync?.sourceMode === 'feishu') {
      return { text: '飞书结果表当前数据已来自飞书结果表，无需同步。', className: 'status-banner neutral' }
    }
    if (sync?.ok) {
      return { text: String(sync.message || `已读取${sourceName}`), className: 'status-banner success' }
    }
    if (sync?.ready) {
      return { text: '检查结果无误后，点击“确认同步飞书”。', className: 'status-banner neutral' }
    }
    return { text: String(sync?.message || '当前来源结果已加载。'), className: 'status-banner neutral' }
  })

  const kpiPeriod = computed(() => {
    const range = displayDateRangeFromRows(currentRows.value)
    const periodText = range ? `${toIsoDate(range.start)} 至 ${toIsoDate(range.end)}` : '当前筛选下无可统计周期'
    return `当前指标统计周期：${filters.metric} · ${filters.period} · ${periodText}`
  })

  const kpis = computed<KpiItem[]>(() => {
    const report = activeReport.value
    if (!report) return []
    const metric = filters.metric
    const compareContext = {
      period: filters.period,
      range: filters.range,
      selected: selectedDateRange(report, reportFilters.value),
    }
    const compareRows = comparisonRows(report, compareContext.period)
    const weightedValue = weightedPercentValue(currentRows.value, metric)
    const marketGap = weightedMarketGap(currentRows.value, metric)
    const weeklyMetric: ComparisonResult = filters.range === 'campaign'
      ? { delta: null, previousValue: null, previousLabel: '', previousTargetLabel: '', unsupported: '活动开启后不统计较上周变化' }
      : metricComparison(currentRows.value, compareRows, metric, (date) => addDays(date, -7), (date) => addDays(date, -7), compareContext)
    const monthShift = previousMonthShiftStart(compareContext.period)
    const monthLabel = '上月'
    const monthlyMetric = metricComparison(currentRows.value, compareRows, metric, monthShift, monthShift, compareContext, { useCampaignControl: true })
    const marketGapWeekly: ComparisonResult = filters.range === 'campaign'
      ? { delta: null, previousValue: null, previousLabel: '', previousTargetLabel: '', unsupported: '活动开启后不统计较上周变化' }
      : marketGapComparison(currentRows.value, compareRows, metric, (date) => addDays(date, -7), (date) => addDays(date, -7), compareContext)
    const marketGapMonthly = marketGapComparison(currentRows.value, compareRows, metric, monthShift, monthShift, compareContext, { useCampaignControl: true })
    const items = [
      {
        label: `加权 ${metric}`,
        value: percentText(weightedValue),
        hint: `当前口径 ${formatNumber(currentRows.value.length)} 行`,
      },
      {
        label: '较上周变化',
        value: ppText(weeklyMetric.delta),
        hint: percentCompareHint('上周', weeklyMetric, compareContext.range),
      },
      {
        label: `较${monthLabel}变化`,
        value: ppText(monthlyMetric.delta),
        hint: percentCompareHint(monthLabel, monthlyMetric, compareContext.range),
      },
      {
        label: '较大盘变化',
        value: ppText(marketGap),
        hint: filters.range === 'all'
          ? '全部范围不支持环比'
          : filters.range === 'campaign'
            ? `较${monthLabel} ${ppText(marketGapMonthly.delta)}`
            : `较上周 ${ppText(marketGapWeekly.delta)} / 较${monthLabel} ${ppText(marketGapMonthly.delta)}`,
      },
    ]
    return items.map((item) => ({ ...item, tone: trendClass(item.value) }))
  })

  const chartRows = computed(() => currentRows.value.slice().sort((left, right) => {
    const leftTime = parseDate(dateValue(left))?.getTime() ?? 0
    const rightTime = parseDate(dateValue(right))?.getTime() ?? 0
    return leftTime - rightTime
  }))
  const chartSubtitle = computed(() => (
    chartRows.value.length
      ? `按 ${filters.metric} 展示当前筛选范围内 ${chartRows.value.length} 行`
      : `当前筛选下没有 ${filters.metric} 数据`
  ))
  const chartLegend = computed(() => {
    const marketField = marketFields[filters.metric]
    return [
      { className: 'blue', label: '用户数' },
      { className: 'orange', label: filters.metric },
      ...(marketField ? [{ className: 'gray', label: marketField }] : []),
    ]
  })
  const chartHtml = computed(() => buildChartHtml(chartRows.value, filters.metric))

  const sources = computed(() => (status.value?.sources || []) as SourceItem[])
  const syncRows = computed<SyncRow[]>(() => {
    const config = (status.value?.config || {}) as Record<string, unknown>
    const sync = (runtime.value?.sync || {}) as SyncPayload
    const rows: SyncRow[] = [
      { key: '数据源', value: filters.dataSource === 'feishu' ? '飞书结果表' : '本地结果文件' },
      { key: '配置', value: config.ready ? '可用' : String(config.message || '不可用') },
      { key: '飞书状态', value: feishuStatusText(sync) },
      { key: '新增', value: String(sync.created ?? sync.createdFields ?? '-') },
      { key: '更新', value: String(sync.updated ?? sync.updatedFields ?? '-') },
    ]
    feishuLinks((config.feishuLinks || []) as Array<{ label?: string; url?: string }>).forEach((row) => rows.push(row))
    return rows
  })
  const messages = computed<MessageItem[]>(() => {
    const items: MessageItem[] = []
    const errors = runtime.value?.errors || []
    const sync = runtime.value?.sync as SyncPayload | undefined
    errors.forEach((error) => items.push({ type: 'error', title: error.title || '错误', body: error.body || '' }))
    if (!runtime.value?.generatedAt) {
      items.push({ type: 'neutral', title: '尚未刷新', body: '点击“刷新数据”后会生成本地 xlsx，确认后才能同步飞书。' })
    } else if (sync?.ready) {
      items.push({ type: 'neutral', title: '等待确认同步', body: '本地结果已生成，请检查图表和明细后再写入飞书。' })
    } else if (sync && !sync.ok && sync.message) {
      items.push({ type: sync.blocked ? 'warning' : 'error', title: sync.blocked ? '飞书同步已阻断' : '飞书同步失败', body: String(sync.message) })
    }
    if (!items.length) {
      items.push({ type: 'success', title: '当前无错误', body: '源文件、计算结果和同步状态会在刷新后更新。' })
    }
    return items
  })

  watchEffect(() => {
    document.body.classList.toggle('side-panel-collapsed', sidePanelCollapsed.value)
    document.body.classList.toggle('nav-collapsed', navCollapsed.value)
  })

  watchEffect(() => {
    const report = activeReport.value
    if (filters.range === 'custom' || !report) return
    const range = selectedDateRange(report, reportFilters.value)
    if (range.start && range.end) {
      filters.customStart = toIsoDate(range.start)
      filters.customEnd = toIsoDate(range.end)
    }
  })

  async function loadInitial() {
    try {
      const [nextStatus, nextRuntime] = await Promise.all([fetchStatus(), fetchReports('feishu')])
      status.value = nextStatus
      runtime.value = nextRuntime
      filters.dataSource = nextRuntime.dataSource || 'feishu'
      fatalMessage.value = ''
    } catch (error) {
      renderFatal(`页面初始化失败：${errorMessage(error)}`)
    }
  }

  async function changeSource(source: ReportSource) {
    if (source === filters.dataSource) return
    loading.value = true
    try {
      filters.dataSource = source
      runtime.value = await fetchReports(source)
      fatalMessage.value = ''
    } catch (error) {
      renderFatal(`读取数据来源失败：${errorMessage(error)}`)
    } finally {
      loading.value = false
    }
  }

  async function refreshReports() {
    loading.value = true
    try {
      const nextRuntime = await requestRefreshReports()
      status.value = nextRuntime.status as StatusPayload
      if (filters.dataSource === 'local') {
        runtime.value = { ...nextRuntime, dataSource: 'local', sourceName: '本地结果文件' }
      } else {
        runtime.value = await fetchReports(filters.dataSource)
      }
      fatalMessage.value = ''
    } catch (error) {
      renderFatal(`刷新失败：${errorMessage(error)}`)
    } finally {
      loading.value = false
    }
  }

  async function syncFeishu() {
    if (!canSyncCurrentLocalResult.value) {
      window.alert('请先刷新数据，再同步飞书。')
      return
    }
    const confirmed = window.confirm('确认将当前 30 日留存结果同步到飞书多维表格？已有记录会更新，汇总表过期自动记录会清理。')
    if (!confirmed) return
    loading.value = true
    try {
      await requestSyncReports()
      status.value = await fetchStatus()
      runtime.value = await fetchReports(filters.dataSource)
      fatalMessage.value = ''
    } catch (error) {
      renderFatal(`飞书同步失败：${errorMessage(error)}`)
    } finally {
      loading.value = false
    }
  }

  function exportCurrentReport() {
    const report = activeReport.value
    if (!report) {
      window.alert('没有可导出的报表，请先刷新数据。')
      return
    }
    const columns = report.fieldnames || []
    if (!columns.length) {
      window.alert('当前报表没有可导出的字段。')
      return
    }
    downloadText(nextExportFilename('30日留存数据', 'csv'), csvText(columns, report.rows || []), 'text/csv;charset=utf-8')
  }

  function toggleSidePanel() {
    sidePanelCollapsed.value = !sidePanelCollapsed.value
    localStorage.setItem('retention30SidePanelCollapsed', String(sidePanelCollapsed.value))
  }

  function toggleNav() {
    navCollapsed.value = !navCollapsed.value
  }

  function renderFatal(message: string) {
    fatalMessage.value = message
  }

  onMounted(loadInitial)

  return {
    filters,
    loading,
    sidePanelCollapsed,
    reportTitle,
    reportDescription,
    lastRefreshText,
    dataDirText,
    syncButtonDisabled,
    notice,
    activeReport,
    hasBlockingErrors,
    kpiPeriod,
    kpis,
    chartSubtitle,
    chartLegend,
    chartHtml,
    sortedRows,
    tableColumns,
    sources,
    syncRows,
    messages,
    changeSource,
    refreshReports,
    syncFeishu,
    exportCurrentReport,
    toggleSidePanel,
    toggleNav,
  }
}

function rowsBetween(rows: ReportRow[], start: Date, end: Date): ReportRow[] {
  return rows.filter((row) => {
    const date = parseDate(dateValue(row))
    return date && date >= start && date <= end
  })
}

function comparisonRows(report: Report, period: string): ReportRow[] {
  return report.rows.filter((row) => row['周期类型'] === period)
}

function rowDateRange(rows: ReportRow[]): DateRange | null {
  const dates = rows
    .map((row) => parseDate(dateValue(row)))
    .filter((date): date is Date => Boolean(date))
    .sort((left, right) => left.getTime() - right.getTime())
  if (!dates.length) return null
  return { start: dates[0], end: dates[dates.length - 1] }
}

function rateDelta(current: number | null, previous: number | null): number | null {
  return current == null || previous == null ? null : current - previous
}

function shiftedDateRange(range: DateRange | null, shiftStart: (date: Date) => Date, shiftEnd: (date: Date) => Date): DateRange | null {
  if (!range?.start || !range.end) return null
  return { start: shiftStart(range.start), end: shiftEnd(range.end) }
}

function campaignControlRange(): DateRange | null {
  const campaignStart = parseDate(CAMPAIGN_START_DATE)
  if (!campaignStart) return null
  return {
    start: new Date(campaignStart.getFullYear(), campaignStart.getMonth() - 1, 1),
    end: addDays(campaignStart, -CAMPAIGN_COMPARE_DAYS),
  }
}

function campaignComparisonRange(range: DateRange | null, fallbackRange: DateRange | null, selectedRange: string): DateRange | null {
  if (selectedRange !== 'campaign' || !range?.end || !fallbackRange?.start) return fallbackRange
  const campaignStart = parseDate(CAMPAIGN_START_DATE)
  if (!campaignStart || fallbackRange.start >= campaignStart) return fallbackRange
  const daysAfterCampaign = Math.floor((range.end.getTime() - campaignStart.getTime()) / 86400000) + 1
  return daysAfterCampaign >= CAMPAIGN_COMPARE_DAYS * 2 ? fallbackRange : campaignControlRange()
}

interface ComparisonOptions {
  useCampaignControl?: boolean
}

interface ComparisonContext {
  period: string
  range: string
  selected: DateRange
}

function comparisonDateRange(currentRows: ReportRow[], selectedRange: string, selected: DateRange): DateRange | null {
  if (selectedRange === 'all') return null
  if (selectedRange === 'campaign') return displayDateRangeFromRows(currentRows) || rowDateRange(currentRows) || selected
  if (selected.start && selected.end) return selected
  return displayDateRangeFromRows(currentRows) || rowDateRange(currentRows)
}

function metricComparison(
  currentRows: ReportRow[],
  allRows: ReportRow[],
  metric: string,
  shiftStart: (date: Date) => Date,
  shiftEnd: (date: Date) => Date,
  context: ComparisonContext,
  options: ComparisonOptions = {},
): ComparisonResult {
  const range = comparisonDateRange(currentRows, context.range, context.selected)
  const shiftedRange = shiftedDateRange(range, shiftStart, shiftEnd)
  const previousRange = options.useCampaignControl ? campaignComparisonRange(range, shiftedRange, context.range) : shiftedRange
  const previousRows = previousRange?.start && previousRange.end ? rowsBetween(allRows, previousRange.start, previousRange.end) : []
  const actualPreviousRange = displayDateRangeFromRows(previousRows) || rowDateRange(previousRows) || previousRange
  const currentValue = weightedPercentValue(currentRows, metric)
  const previousValue = weightedPercentValue(previousRows, metric)
  return {
    delta: rateDelta(currentValue, previousValue),
    previousValue,
    previousLabel: rangeLabel(actualPreviousRange),
    previousTargetLabel: rangeLabel(previousRange),
  }
}

function marketGapComparison(
  currentRows: ReportRow[],
  allRows: ReportRow[],
  metric: string,
  shiftStart: (date: Date) => Date,
  shiftEnd: (date: Date) => Date,
  context: ComparisonContext,
  options: ComparisonOptions = {},
): ComparisonResult {
  const range = comparisonDateRange(currentRows, context.range, context.selected)
  const shiftedRange = shiftedDateRange(range, shiftStart, shiftEnd)
  const previousRange = options.useCampaignControl ? campaignComparisonRange(range, shiftedRange, context.range) : shiftedRange
  const previousRows = previousRange?.start && previousRange.end ? rowsBetween(allRows, previousRange.start, previousRange.end) : []
  const actualPreviousRange = displayDateRangeFromRows(previousRows) || rowDateRange(previousRows) || previousRange
  const currentValue = weightedMarketGap(currentRows, metric)
  const previousValue = weightedMarketGap(previousRows, metric)
  return {
    delta: rateDelta(currentValue, previousValue),
    previousValue,
    previousLabel: rangeLabel(actualPreviousRange),
    previousTargetLabel: rangeLabel(previousRange),
  }
}

function previousMonthShiftStart(period: string): (date: Date) => Date {
  return period === '月' ? (date) => addMonths(date, -1) : (date) => addDays(date, -30)
}

function percentCompareHint(label: string, comparison: ComparisonResult, selectedRange: string): string {
  if (comparison.unsupported) return comparison.unsupported
  if (selectedRange === 'all') return '全部范围不支持环比'
  if (!comparison.previousLabel) return `无${label}数据`
  const period = comparison.previousTargetLabel && comparison.previousTargetLabel !== comparison.previousLabel
    ? `${comparison.previousTargetLabel}（实际 ${comparison.previousLabel}）`
    : comparison.previousLabel
  return `${label} ${period}：${percentText(comparison.previousValue)}`
}

function formatNumber(value: unknown): string {
  const number = Number(String(value ?? '').replace(/,/g, ''))
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : String(value || '-')
}

function percentText(value: number | null): string {
  return value == null || !Number.isFinite(value) ? '-' : `${(value * 100).toFixed(2)}%`
}

function ppText(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(2)}pp`
}

function trendClass(value: unknown): string {
  const number = Number(String(value ?? '').replace(/,/g, '').replace('%', '').replace('pp', ''))
  if (!Number.isFinite(number) || number === 0) return 'neutral'
  return number > 0 ? 'positive' : 'negative'
}

function buildChartHtml(rows: ReportRow[], metric: string): string {
  const marketField = marketFields[metric]
  if (!rows.length) return '<div class="empty">没有可绘制的数据</div>'
  const height = 320
  const padding = { top: 28, right: 58, bottom: 54, left: 72 }
  const width = Math.max(960, padding.left + padding.right + rows.length * 86)
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom
  const maxUsers = Math.max(...rows.map((row) => Number(row['用户数']) || 0), 1)
  const rateValues = rows
    .flatMap((row) => [percentToNumber(row[metric]), marketField ? percentToNumber(row[marketField]) : null])
    .filter((value): value is number => value != null)
  const maxRate = Math.max(...rateValues, 0.01)
  const band = innerWidth / rows.length
  const barWidth = Math.min(30, band / 3)
  const x = (index: number) => padding.left + index * band + band / 2
  const yUsers = (value: number) => padding.top + innerHeight - (value / maxUsers) * innerHeight
  const yRate = (value: number) => padding.top + innerHeight - (value / maxRate) * innerHeight
  const linePoints = rows
    .map((row, index) => {
      const value = percentToNumber(row[metric])
      return value == null ? '' : `${x(index)},${yRate(value)}`
    })
    .filter(Boolean)
    .join(' ')
  const marketPoints = rows
    .map((row, index) => {
      const value = marketField ? percentToNumber(row[marketField]) : null
      return value == null ? '' : `${x(index)},${yRate(value)}`
    })
    .filter(Boolean)
    .join(' ')
  const grid = [0, 0.25, 0.5, 0.75, 1].map((tick) => {
    const gy = padding.top + innerHeight * tick
    const label = Math.round(maxUsers * (1 - tick)).toLocaleString('zh-CN')
    return `<line x1="${padding.left}" y1="${gy}" x2="${width - padding.right}" y2="${gy}" class="grid-line" />
      <text x="${padding.left - 12}" y="${gy + 4}" text-anchor="end" class="axis-label">${label}</text>`
  }).join('')
  const bars = rows.map((row, index) => {
    const cx = x(index)
    const users = Number(row['用户数']) || 0
    const rate = percentToNumber(row[metric])
    const marketRate = marketField ? percentToNumber(row[marketField]) : null
    const label = periodLabel(row)
    return `
      <rect x="${cx - barWidth / 2}" y="${yUsers(users)}" width="${barWidth}" height="${padding.top + innerHeight - yUsers(users)}" rx="3" class="bar blue" />
      <text x="${cx}" y="${yUsers(users) - 6}" text-anchor="middle" class="user-label">${formatNumber(users)}</text>
      ${rate == null ? '' : `<circle cx="${cx}" cy="${yRate(rate)}" r="4" class="rate-dot" />
      <text x="${cx}" y="${yRate(rate) - 10}" text-anchor="middle" class="rate-label">${escapeHtml(row[metric])}</text>`}
      ${marketRate == null ? '' : `<circle cx="${cx}" cy="${yRate(marketRate)}" r="4" class="market-dot" />`}
      <text x="${cx}" y="${height - 20}" text-anchor="middle" class="axis-label">${escapeHtml(label)}</text>`
  }).join('')
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
    ${grid}
    <line x1="${padding.left}" y1="${padding.top + innerHeight}" x2="${width - padding.right}" y2="${padding.top + innerHeight}" class="axis-line" />
    ${bars}
    ${linePoints ? `<polyline points="${linePoints}" class="rate-line" />` : ''}
    ${marketPoints ? `<polyline points="${marketPoints}" class="market-line" />` : ''}
  </svg>`
}

function feishuStatusText(sync: SyncPayload): string {
  if (sync.ok) return '成功'
  if (sync.ready) return '等待确认'
  if (sync.blocked) return String(sync.message || '已阻断')
  return String(sync.message || '尚未同步')
}

function feishuLinks(links: Array<{ label?: string; url?: string }>): SyncRow[] {
  const items = links.length ? links : [{ label: '飞书结果表', url: '' }]
  return items.map((item) => ({
    key: normalizeFeishuLinkLabel(item.label),
    url: item.url || '',
    disabled: !item.url,
  }))
}

function normalizeFeishuLinkLabel(label?: string): string {
  if (!label || label === '飞书结果表') return '飞书链接'
  return label.replace(/^飞书结果表/, '飞书链接')
}

function nextExportFilename(reportTitle: string, extension: string): string {
  const base = `${safeFilePart(reportTitle)}_${exportTimestamp()}`
  const key = `retention30-export-${base}.${extension}`
  const count = Number(localStorage.getItem(key) || '0') + 1
  localStorage.setItem(key, String(count))
  const suffix = count === 1 ? '' : `_${String(count).padStart(2, '0')}`
  return `${base}${suffix}.${extension}`
}

function downloadText(filename: string, text: string, type: string) {
  const bytes = new TextEncoder().encode(text)
  const blob = new Blob([bytes], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
