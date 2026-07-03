// 新锐攻略接口模块：集中定义看板前端请求入口。

export interface RuntimePayload {
  generatedAt?: string
  lastSuccessfulRefresh?: string
  sourceMode?: 'feishu' | 'local'
  reports?: Array<Record<string, unknown>>
  errors?: Array<{ id?: string; title?: string; body?: string }>
  sync?: Record<string, unknown>
  status?: StatusPayload
}

export interface StatusPayload {
  appDir?: string
  dataDir?: string
  outputDir?: string
  sourceMode?: 'feishu' | 'local'
  sourceModes?: Array<'feishu' | 'local'>
  sources?: Array<Record<string, unknown>>
  config?: Record<string, unknown>
  lastRefresh?: string
  lastSync?: Record<string, unknown>
}

export async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', ...options })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function fetchStatus(): Promise<StatusPayload> {
  return fetchJson<StatusPayload>('/api/status')
}

export function fetchReports(): Promise<RuntimePayload> {
  return fetchJson<RuntimePayload>('/api/reports')
}

export function refreshReports(sourceMode: 'feishu' | 'local'): Promise<RuntimePayload> {
  return fetchJson<RuntimePayload>('/api/refresh', {
    method: 'POST',
    body: JSON.stringify({ sourceMode }),
  })
}

export function syncReports(): Promise<RuntimePayload> {
  return fetchJson<RuntimePayload>('/api/sync', { method: 'POST', body: '{}' })
}
