// CSV 工具测试：验证导出命名、转义和 UTF-8 BOM。

import { describe, expect, it } from 'vitest'

import { csvCell, csvText, exportFilename } from './csv'

describe('csv utils', () => {
  it('生成 GDATA 报表导出文件名', () => {
    const date = new Date(2026, 6, 3, 11, 41)

    expect(exportFilename('新用户转化率', 'csv', date)).toBe('新用户转化率_2026-07-03_11点41分.csv')
  })

  it('按 CSV 规则转义单元格', () => {
    expect(csvCell('a,b"c')).toBe('"a,b""c"')
  })

  it('导出文本包含 UTF-8 BOM', () => {
    const text = csvText(['统计周期'], [{ 统计周期: '6.01' }])

    expect(text.charCodeAt(0)).toBe(0xfeff)
    expect(text).toBe('\ufeff统计周期\r\n6.01')
  })
})
