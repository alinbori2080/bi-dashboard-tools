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
  assert.match(appVue, /本地结果文件/);
  assert.match(appVue, /后续留存数据/);
  assert.match(appVue, /导出全部/);
  assert.match(appVue, /dashboard\.filters\.period === '日'/);
  assert.match(appVue, /dashboard\.filters\.period === '周'/);
  assert.match(appVue, /dashboard\.filters\.period === '月'/);
  assert.match(appVue, /dashboard\.filters\.metric === '21日留'/);
});

test('新版前端控制器保留关键业务动作', () => {
  const controller = fs.readFileSync(path.resolve(__dirname, '../frontend/src/composables/useRetentionDashboard.ts'), 'utf8');

  assert.match(controller, /async function refreshReports/);
  assert.match(controller, /async function syncFeishu/);
  assert.match(controller, /function exportCurrentReport/);
  assert.match(controller, /csvText\(columns, report\.rows \|\| \[\]\)/);
  assert.match(controller, /活动开启后不统计较上周变化/);
});
