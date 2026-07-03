const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('静态回退页不再加载旧版 app.js', () => {
  const html = fs.readFileSync(path.resolve(__dirname, '../static/index.html'), 'utf8');

  assert.match(html, /静态回退提示页/);
  assert.match(html, /npm run build/);
  assert.doesNotMatch(html, /<script[^>]+app\.js/);
});

test('新版 Vue 页面保留核心筛选入口', () => {
  const appVue = fs.readFileSync(path.resolve(__dirname, '../frontend/src/App.vue'), 'utf8');

  assert.match(appVue, /飞书结果表/);
  assert.match(appVue, /本地文件/);
  assert.match(appVue, /推送用户留存付费/);
  assert.match(appVue, /导出 CSV/);
  assert.match(appVue, /data-dimension="日"/);
  assert.match(appVue, /data-dimension="周"/);
  assert.match(appVue, /data-dimension="月"/);
});

test('新版前端控制器保留关键业务动作和日维度逻辑', () => {
  const controller = fs.readFileSync(path.resolve(__dirname, '../frontend/src/composables/useNewbieDashboard.ts'), 'utf8');

  assert.match(controller, /async function refreshData/);
  assert.match(controller, /async function syncFeishu/);
  assert.match(controller, /function exportCurrentReport/);
  assert.match(controller, /function periodRows/);
  assert.match(controller, /dimension === "日"/);
  assert.match(controller, /csvText\(displayFields, displayRows\(\)\)/);
});
