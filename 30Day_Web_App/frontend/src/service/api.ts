// 30 日留存接口模块：集中定义看板前端请求入口。

import type { ReportSource, RuntimePayload, StatusPayload } from '@/types/report'

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

export function fetchReports(source: ReportSource): Promise<RuntimePayload> {
  return fetchJson<RuntimePayload>(`/api/reports?source=${encodeURIComponent(source)}`)
}

export function refreshReports(): Promise<RuntimePayload> {
  return fetchJson<RuntimePayload>('/api/refresh', { method: 'POST' })
}

export function syncReports(): Promise<RuntimePayload> {
  return fetchJson<RuntimePayload>('/api/sync', { method: 'POST' })
}
