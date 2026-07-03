// 30 日留存看板兼容桥接：加载现有原生 JS 业务逻辑。

let legacyLoaded = false

export async function mountRetentionDashboard() {
  if (legacyLoaded) return
  legacyLoaded = true
  const legacyScriptUrl = `${window.location.origin}/app.js`
  await import(/* @vite-ignore */ legacyScriptUrl)
}
