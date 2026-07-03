// CSV 工具模块：处理导出文件名和 UTF-8 BOM 文本。

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

export function exportTimestamp(date = new Date()): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}_${pad2(date.getHours())}点${pad2(date.getMinutes())}分`
}

export function safeFilePart(value: unknown): string {
  return (
    String(value || 'report')
      .trim()
      .replace(/[<>:"/\\|?*\x00-\x1F]/g, '_')
      .replace(/\s+/g, ' ')
      .slice(0, 80) || 'report'
  )
}

export function exportFilename(reportTitle: string, extension: string, date = new Date()): string {
  return `${safeFilePart(reportTitle)}_${exportTimestamp(date)}.${extension}`
}

export function csvCell(value: unknown): string {
  const text = String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function csvText(columns: string[], rows: Array<Record<string, unknown>>): string {
  const lines = [
    columns.map(csvCell).join(','),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(',')),
  ]
  return `\ufeff${lines.join('\r\n')}`
}
