// 报表计算工具测试：验证筛选、日期和指标口径与旧看板一致。

import { describe, expect, it } from 'vitest'

import type { Report } from '@/types/report'

import {
  addDays,
  addMonths,
  displayDateRangeFromRows,
  displayRowsFor,
  latestDate,
  rangeLabel,
  rowsFor,
  selectedDateRange,
  toIsoDate,
  weightedMarketGap,
  weightedPercentValue,
} from './report'

describe('report utils', () => {
  const report: Report = {
    id: 'daily',
    title: '每日结果',
    rows: [
      { 统计周期: '6.01', 周期类型: '日', 开始日期: '2026-06-01', 结束日期: '2026-06-01', 用户数: 10, 次留: '10.00%' },
      { 统计周期: '6.02', 周期类型: '日', 开始日期: '2026-06-02', 结束日期: '2026-06-02', 用户数: 20, 次留: '20.00%' },
      { 统计周期: '6.01-6.07', 周期类型: '周', 开始日期: '2026-06-01', 结束日期: '2026-06-07', 用户数: 70, 次留: '30.00%' },
      { 统计周期: '6.01-6.30', 周期类型: '月', 开始日期: '2026-06-01', 结束日期: '2026-06-30', 用户数: 300, 次留: '40.00%' },
    ],
  }

  it('按周期类型筛选日周月', () => {
    expect(rowsFor(report, { range: 'all', period: '日' }).map((row) => row['统计周期'])).toEqual(['6.01', '6.02'])
    expect(rowsFor(report, { range: 'all', period: '周' }).map((row) => row['统计周期'])).toEqual(['6.01-6.07'])
    expect(rowsFor(report, { range: 'all', period: '月' }).map((row) => row['统计周期'])).toEqual(['6.01-6.30'])
  })

  it('按结束日期倒序展示明细', () => {
    expect(displayRowsFor(report, { range: 'all', period: '日' }).map((row) => row['统计周期'])).toEqual([
      '6.02',
      '6.01',
    ])
  })

  it('近 N 天使用报表内最大结束日期倒推', () => {
    const range = selectedDateRange(report, { range: '7', period: '日' })

    expect(toIsoDate(range.start)).toBe('2026-06-24')
    expect(toIsoDate(range.end)).toBe('2026-06-30')
  })

  it('活动开启后从固定日期统计到最新日期', () => {
    const range = selectedDateRange(report, {
      range: 'campaign',
      period: '日',
      campaignStartDate: '2026-05-26',
    })

    expect(toIsoDate(range.start)).toBe('2026-05-26')
    expect(toIsoDate(range.end)).toBe('2026-06-30')
  })

  it('自定义范围只保留范围内日期', () => {
    const rows = rowsFor(report, {
      range: 'custom',
      period: '日',
      customStart: '2026-06-02',
      customEnd: '2026-06-02',
    })

    expect(rows.map((row) => row['统计周期'])).toEqual(['6.02'])
  })

  it('计算日期范围标签', () => {
    const range = displayDateRangeFromRows(report.rows)

    expect(toIsoDate(latestDate(report))).toBe('2026-06-30')
    expect(rangeLabel(range)).toBe('6.01-6.30')
  })

  it('按用户数加权计算留存率', () => {
    const value = weightedPercentValue(
      [
        { 用户数: 100, 次留: '10.00%' },
        { 用户数: 300, 次留: '30.00%' },
      ],
      '次留',
    )

    expect(value).toBe(0.25)
  })

  it('较大盘只统计双方都有值的行', () => {
    const value = weightedMarketGap(
      [
        { 用户数: 100, '7日留': '40.00%', 大盘7日留: '20.00%' },
        { 用户数: 100, '7日留': '-', 大盘7日留: '10.00%' },
      ],
      '7日留',
    )

    expect(value).toBe(0.2)
  })

  it('日期平移保留旧口径', () => {
    expect(toIsoDate(addDays(new Date(2026, 5, 1), -7))).toBe('2026-05-25')
    expect(toIsoDate(addMonths(new Date(2026, 2, 31), -1))).toBe('2026-02-28')
  })
})
