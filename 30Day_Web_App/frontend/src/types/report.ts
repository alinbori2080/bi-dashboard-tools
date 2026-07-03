// 30 日留存类型声明：描述报表、运行状态和同步状态。

export interface ReportRow {
  [field: string]: string | number | null | undefined
}

export interface Report {
  id: string
  title: string
  description?: string
  fieldnames?: string[]
  rows: ReportRow[]
}

export interface RuntimePayload {
  generatedAt?: string
  dataSource?: 'feishu' | 'local'
  sourceName?: string
  reports?: Report[]
  errors?: Array<{ id?: string; title?: string; body?: string }>
  sync?: Record<string, unknown>
}

export type ReportSource = 'feishu' | 'local'

export interface StatusPayload {
  appDir?: string
  dataDir?: string
  outputDir?: string
  sourceModes?: ReportSource[]
  sources?: Array<Record<string, unknown>>
  config?: Record<string, unknown>
  lastRefresh?: string
  lastSync?: Record<string, unknown>
}
