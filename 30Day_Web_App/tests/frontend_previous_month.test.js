const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('页面提供21日留指标入口', () => {
  const html = fs.readFileSync(path.resolve(__dirname, '../static/index.html'), 'utf8');
  assert.match(html, /data-metric="21日留"/);
});

test('页面只保留每日结果并提供日周月维度', () => {
  const html = fs.readFileSync(path.resolve(__dirname, '../static/index.html'), 'utf8');
  assert.doesNotMatch(html, /data-report="summary"/);
  assert.match(html, /data-period="日"/);
  assert.match(html, /data-period="周"/);
  assert.match(html, /data-period="月"/);
});

function createElement() {
  return {
    classList: { toggle() {} },
    dataset: {},
    disabled: false,
    textContent: '',
    value: '',
    addEventListener() {},
    appendChild() {},
    remove() {},
    closest() { return null; },
    querySelectorAll() { return []; },
    setAttribute() {},
  };
}

function loadAppContext() {
  const appPath = path.resolve(__dirname, '../static/app.js');
  const source = fs.readFileSync(appPath, 'utf8').replace(/\nloadInitial\(\);\s*$/, '');
  const elements = {};
  const context = {
    Blob: function Blob() {},
    URL: { createObjectURL() { return ''; }, revokeObjectURL() {} },
    document: {
      body: { classList: { toggle() {} }, appendChild() {} },
      createElement,
      querySelector(selector) {
        elements[selector] ||= createElement();
        return elements[selector];
      },
      querySelectorAll() { return []; },
    },
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    localStorage: { getItem() { return null; }, setItem() {} },
    window: { alert() {}, confirm() { return false; } },
    __elements: elements,
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

test('较上月倒推30天且只统计实际存在日期', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = '30';
    state.activeReport = 'daily';
    state.metric = '次留';
    state.runtime = {
      reports: [{
        id: 'daily',
        rows: [
          { '统计周期': '4.01', '周期类型': '日', '开始日期': '2026-04-01', '结束日期': '2026-04-01', '用户数': 100, '次留': '10.00%' },
          { '统计周期': '4.26', '周期类型': '日', '开始日期': '2026-04-26', '结束日期': '2026-04-26', '用户数': 100, '次留': '30.00%' },
          { '统计周期': '4.27', '周期类型': '日', '开始日期': '2026-04-27', '结束日期': '2026-04-27', '用户数': 100, '次留': '40.00%' },
          { '统计周期': '5.26', '周期类型': '日', '开始日期': '2026-05-26', '结束日期': '2026-05-26', '用户数': 100, '次留': '60.00%' }
        ]
      }]
    };
    const report = activeReport();
    const currentRows = rowsFor(report);
    globalThis.label = previousMonthLabel(report);
    globalThis.result = metricComparison(
      report,
      currentRows,
      comparisonRows(report),
      '次留',
      (date) => addDays(date, -30),
      (date) => addDays(date, -30)
    );
  `, context);

  assert.equal(context.label, '上月');
  assert.equal(context.result.previousLabel, '4.01-4.26');
  assert.equal(context.result.previousValue, 0.2);
  assert.equal(context.result.delta, 0.3);
});

test('较大盘变化只统计私域和大盘都有值的日期', () => {
  const context = loadAppContext();
  vm.runInContext(`
    globalThis.result = weightedMarketGap([
      { '日期': '2026-06-15', '用户数': 100, '7日留': '40.00%', '大盘7日留': '20.00%' },
      { '日期': '2026-06-16', '用户数': 100, '7日留': '-', '大盘7日留': '10.00%' }
    ], '7日留');
  `, context);

  assert.equal(context.result, 0.2);
});

test('单一每日结果按周期类型切换日周月', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = 'all';
    state.runtime = {
      reports: [{
        id: 'daily',
        rows: [
          { '统计周期': '6.01', '周期类型': '日', '开始日期': '2026-06-01', '结束日期': '2026-06-01', '用户数': 10 },
          { '统计周期': '6.01-6.07', '周期类型': '周', '开始日期': '2026-06-01', '结束日期': '2026-06-07', '用户数': 70 },
          { '统计周期': '6.01-6.30', '周期类型': '月', '开始日期': '2026-06-01', '结束日期': '2026-06-30', '用户数': 300 }
        ]
      }]
    };
    const report = activeReport();
    state.period = '日';
    globalThis.dayRows = JSON.stringify(rowsFor(report).map((row) => row['统计周期']));
    state.period = '周';
    globalThis.weekRows = JSON.stringify(rowsFor(report).map((row) => row['统计周期']));
    state.period = '月';
    globalThis.monthRows = JSON.stringify(rowsFor(report).map((row) => row['统计周期']));
  `, context);

  assert.equal(context.dayRows, '["6.01"]');
  assert.equal(context.weekRows, '["6.01-6.07"]');
  assert.equal(context.monthRows, '["6.01-6.30"]');
});

test('导出全部不受当前周期筛选影响', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = 'all';
    state.period = '日';
    state.runtime = {
      reports: [{
        id: 'daily',
        title: '每日结果',
        fieldnames: ['统计周期', '周期类型', '用户数'],
        rows: [
          { '统计周期': '6.01', '周期类型': '日', '用户数': 10 },
          { '统计周期': '6.01-6.07', '周期类型': '周', '用户数': 70 },
          { '统计周期': '6.01-6.30', '周期类型': '月', '用户数': 300 }
        ]
      }]
    };
    downloadText = (filename, text) => {
      globalThis.exportFilename = filename;
      globalThis.exportText = text;
    };
    exportCurrentReport();
  `, context);

  assert.match(context.exportFilename, /^30日留存数据_/);
  assert.match(context.exportText, /6\.01,日,10/);
  assert.match(context.exportText, /6\.01-6\.07,周,70/);
  assert.match(context.exportText, /6\.01-6\.30,月,300/);
});

test('导出CSV包含UTF-8 BOM', () => {
  const context = loadAppContext();
  vm.runInContext(`
    globalThis.csv = csvText(['统计周期'], [{ '统计周期': '6.01' }]);
  `, context);

  assert.equal(context.csv.charCodeAt(0), 0xfeff);
  assert.match(context.csv, /^\ufeff统计周期\r\n6\.01$/);
});

test('活动开启后未满60天时对照组固定为4月1日至4月26日', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = 'campaign';
    state.activeReport = 'daily';
    state.metric = '次留';
    state.runtime = {
      reports: [{
        id: 'daily',
        rows: [
          { '统计周期': '4.01', '周期类型': '日', '开始日期': '2026-04-01', '结束日期': '2026-04-01', '用户数': 100, '次留': '10.00%' },
          { '统计周期': '4.26', '周期类型': '日', '开始日期': '2026-04-26', '结束日期': '2026-04-26', '用户数': 100, '次留': '20.00%' },
          { '统计周期': '5.26', '周期类型': '日', '开始日期': '2026-05-26', '结束日期': '2026-05-26', '用户数': 100, '次留': '80.00%' },
          { '统计周期': '5.29', '周期类型': '日', '开始日期': '2026-05-29', '结束日期': '2026-05-29', '用户数': 100, '次留': '90.00%' },
          { '统计周期': '6.28', '周期类型': '日', '开始日期': '2026-06-28', '结束日期': '2026-06-28', '用户数': 100, '次留': '60.00%' }
        ]
      }]
    };
    const report = activeReport();
    const currentRows = rowsFor(report);
    const currentKpiRows = kpiRows(report, currentRows);
    globalThis.currentRange = displayDateRangeFromRows(report, currentKpiRows);
    globalThis.result = metricComparison(
      report,
      currentKpiRows,
      comparisonRows(report),
      '次留',
      (date) => addDays(date, -30),
      (date) => addDays(date, -30),
      { useCampaignControl: true }
    );
    globalThis.weekResult = metricComparison(
      report,
      currentKpiRows,
      comparisonRows(report),
      '次留',
      (date) => addDays(date, -7),
      (date) => addDays(date, -7)
    );
    renderKpis(report);
    globalThis.kpiHtml = __elements['#kpiGrid'].innerHTML;
  `, context);

  assert.equal(context.result.previousTargetLabel, '4.01-4.26');
  assert.equal(context.result.previousLabel, '4.01-4.26');
  assert.equal(context.result.previousValue, 0.15);
  assert.equal(context.result.delta, 0.6166666666666667);
  assert.equal(context.weekResult.previousTargetLabel, '5.19-6.21');
  assert.equal(context.weekResult.previousLabel, '5.26-5.29');
  assert.match(context.kpiHtml, /活动开启后不统计较上周变化/);
  assert.doesNotMatch(context.kpiHtml, /较上周 \\+/);
  assert.doesNotMatch(context.kpiHtml, /较上周 -/);
  assert.equal(context.currentRange.start.toISOString().slice(0, 10), '2026-05-26');
  assert.equal(context.currentRange.end.toISOString().slice(0, 10), '2026-06-28');
});
