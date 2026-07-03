// CSV 工具测试：验证导出命名、转义和 UTF-8 BOM。

import { describe, expect, it } from 'vitest'

import { csvCell, csvText, exportFilename } from './csv'

describe('csv utils', () => {
  it('生成新锐看板导出文件名', () => {
    const date = new Date(2026, 6, 3, 11, 41)

    expect(exportFilename('推送用户留存付费汇总', 'csv', date)).toBe('推送用户留存付费汇总_2026-07-03_11点41分.csv')
  })

  it('按 CSV 规则转义单元格', () => {
    expect(csvCell('a,b"c')).toBe('"a,b""c"')
  })

  it('导出文本包含 UTF-8 BOM', () => {
    const text = csvText(['推送批次'], [{ 推送批次: '6月01日' }])

    expect(text.charCodeAt(0)).toBe(0xfeff)
    expect(text).toBe('\ufeff推送批次\r\n6月01日')
  })
})
