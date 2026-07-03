// GDATA 接口测试：验证统一请求封装和业务 API 路径。

import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchJson, fetchReports, fetchStatus, refreshReports, syncReports } from './api'

describe('api service', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('默认禁用缓存并返回 JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchJson('/api/status')).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/status', { cache: 'no-store' })
  })

  it('HTTP 非成功状态抛出状态码', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    await expect(fetchJson('/api/status')).rejects.toThrow('HTTP 500')
  })

  it('封装看板 API 路径', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchStatus()
    await fetchReports()
    await refreshReports('local')
    await syncReports()

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/status', { cache: 'no-store' })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/reports', { cache: 'no-store' })
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/refresh', { cache: 'no-store', method: 'POST', body: '{"sourceMode":"local"}' })
    expect(fetchMock).toHaveBeenNthCalledWith(4, '/api/sync', { cache: 'no-store', method: 'POST', body: '{}' })
  })
})
