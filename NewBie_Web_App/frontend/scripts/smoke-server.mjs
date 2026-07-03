// 新锐攻略服务冒烟测试：验证后端能服务 Vite 构建页面和核心 API。

import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

const port = 8892
const baseUrl = `http://127.0.0.1:${port}`
const appDir = new URL('../..', import.meta.url)
const server = spawn('python', ['-B', 'server.py', String(port)], {
  cwd: appDir,
  env: {
    ...process.env,
    PYTHONDONTWRITEBYTECODE: '1',
    PYTHONUTF8: '1',
  },
  stdio: ['ignore', 'pipe', 'pipe'],
})

let stdout = ''
let stderr = ''
server.stdout.on('data', (chunk) => {
  stdout += chunk.toString()
})
server.stderr.on('data', (chunk) => {
  stderr += chunk.toString()
})

try {
  await waitForServer()
  const html = await fetchText(`${baseUrl}/`)
  assertIncludes(html, '/assets/index-', '首页没有返回 Vite 构建入口')

  const status = await fetchJson(`${baseUrl}/api/status`)
  if (!status || typeof status !== 'object' || !('dataDir' in status)) {
    throw new Error('/api/status 未返回预期状态结构')
  }

  console.log('newbie smoke server ok')
} finally {
  server.kill('SIGTERM')
}

async function waitForServer() {
  const startedAt = Date.now()
  while (Date.now() - startedAt < 10000) {
    if (server.exitCode != null) {
      throw new Error(`服务提前退出：stdout=${stdout}; stderr=${stderr}`)
    }
    try {
      await fetchText(`${baseUrl}/`)
      return
    } catch {
      await delay(250)
    }
  }
  throw new Error(`服务启动超时：stdout=${stdout}; stderr=${stderr}`)
}

async function fetchText(url) {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) throw new Error(`${url} HTTP ${response.status}`)
  return response.text()
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) throw new Error(`${url} HTTP ${response.status}`)
  return response.json()
}

function assertIncludes(text, pattern, message) {
  if (!text.includes(pattern)) throw new Error(message)
}
