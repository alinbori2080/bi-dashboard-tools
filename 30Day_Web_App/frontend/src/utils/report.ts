// 报表计算工具：处理 30 日留存筛选、日期范围和加权指标计算。

import type { Report, ReportRow } from '@/types/report'

export interface DateRange {
  start: Date | null
  end: Date | null
}

export interface ReportFilters {
  range: 'all' | 'campaign' | 'custom' | string
  period: string
  customStart?: string
  customEnd?: string
  campaignStartDate?: string
}

export const marketFields: Record<string, string> = {
  次留: '大盘次留',
  '3日留': '大盘3日留',
  '7日留': '大盘7日留',
}

export function parseDate(value: unknown): Date | null {
  const time = Date.parse(String(value ?? ''))
  return Number.isFinite(time) ? new Date(time) : null
}

export function toIsoDate(date: Date | null | undefined): string {
  if (!date) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function dateValue(row: ReportRow): string | number | null | undefined {
  return row['结束日期'] || row['开始日期']
}

export function periodLabel(row: ReportRow): string {
  return String(row['统计周期'] || '')
}

export function latestDate(report: Pick<Report, 'rows'> | null | undefined): Date | null {
  const dates = (report?.rows || [])
    .map((row) => parseDate(dateValue(row)))
    .filter((date): date is Date => Boolean(date))
    .sort((left, right) => left.getTime() - right.getTime())
  return dates.length ? dates[dates.length - 1] : null
}

export function selectedDateRange(report: Pick<Report, 'rows'> | null | undefined, filters: ReportFilters): DateRange {
  if (filters.range === 'all') {
    return { start: null, end: null }
  }
  if (filters.range === 'campaign') {
    return {
      start: parseDate(filters.campaignStartDate || '2026-05-26'),
      end: latestDate(report),
    }
  }
  if (filters.range === 'custom') {
    return {
      start: parseDate(filters.customStart),
      end: parseDate(filters.customEnd),
    }
  }
  const end = latestDate(report)
  if (!end) return { start: null, end: null }
  const start = new Date(end)
  start.setDate(start.getDate() - Number(filters.range) + 1)
  return { start, end }
}

export function rowInRange(row: ReportRow, range: DateRange): boolean {
  const date = parseDate(dateValue(row))
  if (!date) return false
  if (range.start && date < range.start) return false
  if (range.end && date > range.end) return false
  return true
}

export function rowsFor(report: Pick<Report, 'rows'> | null | undefined, filters: ReportFilters): ReportRow[] {
  const range = selectedDateRange(report, filters)
  return (report?.rows || []).filter((row) => row['周期类型'] === filters.period && rowInRange(row, range))
}

export function displayRowsFor(report: Pick<Report, 'rows'> | null | undefined, filters: ReportFilters): ReportRow[] {
  return rowsFor(report, filters)
    .slice()
    .sort((left, right) => {
      const leftTime = parseDate(dateValue(left))?.getTime() ?? Number.NEGATIVE_INFINITY
      const rightTime = parseDate(dateValue(right))?.getTime() ?? Number.NEGATIVE_INFINITY
      return rightTime - leftTime
    })
}

export function percentToNumber(value: unknown): number | null {
  const text = String(value ?? '').replace('%', '').trim()
  if (!text || text === '-') return null
  const number = Number(text)
  return Number.isFinite(number) ? number / 100 : null
}

export function weightedPercentValue(rows: ReportRow[], field: string): number | null {
  let weightedSum = 0
  let users = 0
  rows.forEach((row) => {
    const value = percentToNumber(row[field])
    if (value == null) return
    const rowUsers = Number(row['用户数']) || 0
    weightedSum += rowUsers * value
    users += rowUsers
  })
  return users ? weightedSum / users : null
}

export function weightedMarketGap(rows: ReportRow[], metric: string): number | null {
  const marketField = marketFields[metric]
  if (!marketField) return null
  const comparableRows = rows.filter(
    (row) => percentToNumber(row[metric]) != null && percentToNumber(row[marketField]) != null,
  )
  const value = weightedPercentValue(comparableRows, metric)
  const marketValue = weightedPercentValue(comparableRows, marketField)
  return value == null || marketValue == null ? null : value - marketValue
}

export function addDays(date: Date, days: number): Date {
  const result = new Date(date)
  result.setDate(result.getDate() + days)
  return result
}

export function addMonths(date: Date, months: number): Date {
  const targetMonth = date.getMonth() + months
  const lastDay = new Date(date.getFullYear(), targetMonth + 1, 0).getDate()
  return new Date(date.getFullYear(), targetMonth, Math.min(date.getDate(), lastDay))
}

export function displayDateRangeFromRows(rows: ReportRow[]): DateRange | null {
  const starts = rows
    .map((row) => parseDate(row['开始日期'] || row['结束日期']))
    .filter((date): date is Date => Boolean(date))
    .sort((left, right) => left.getTime() - right.getTime())
  const ends = rows
    .map((row) => parseDate(row['结束日期'] || row['开始日期']))
    .filter((date): date is Date => Boolean(date))
    .sort((left, right) => left.getTime() - right.getTime())
  if (!starts.length || !ends.length) return null
  return { start: starts[0], end: ends[ends.length - 1] }
}

export function rangeLabel(range: DateRange | null | undefined): string {
  if (!range?.start || !range?.end) return ''
  const start = `${range.start.getMonth() + 1}.${String(range.start.getDate()).padStart(2, '0')}`
  const end = `${range.end.getMonth() + 1}.${String(range.end.getDate()).padStart(2, '0')}`
  return start === end ? start : `${start}-${end}`
}
