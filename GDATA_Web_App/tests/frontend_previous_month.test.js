const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function createElement() {
  return {
    classList: { toggle() {} },
    dataset: {},
    disabled: false,
    textContent: '',
    value: '',
    addEventListener() {},
    closest() { return null; },
    querySelectorAll() { return []; },
  };
}

function loadAppContext() {
  const appPath = path.resolve(__dirname, '../static/app.js');
  const source = fs.readFileSync(appPath, 'utf8').replace(/\nloadInitial\(\);\s*$/, '');
  const elements = {};
  const context = {
    Blob: function Blob() {},
    URL: { createObjectURL() { return ''; }, revokeObjectURL() {} },
    __elements: elements,
    document: {
      body: { classList: { toggle() {} } },
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
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

test('较上月按当前筛选开始月份取上一个月周期数据', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = '7';
    state.compareDimension = '周';
    state.runtime = {
      reports: [{
        id: 'conversion',
        numeratorField: '新增客户数_SCRM',
        denominatorField: '新登账号_GDATA',
        rows: [
          { '周期类型': '周', '统计周期': '5.04-5.10', '开始日期': '2026-05-04', '结束日期': '2026-05-10', '新增客户数_SCRM': 20, '新登账号_GDATA': 100 },
          { '周期类型': '月', '统计周期': '5月', '开始日期': '2026-05-01', '结束日期': '2026-05-31', '新增客户数_SCRM': 40, '新登账号_GDATA': 100 },
          { '周期类型': '周', '统计周期': '6.01-6.07', '开始日期': '2026-06-01', '结束日期': '2026-06-07', '新增客户数_SCRM': 80, '新登账号_GDATA': 100 }
        ]
      }]
    };
    const report = state.runtime.reports[0];
    const currentRows = rowsFor(report);
    globalThis.result = previousMonthChange(report, currentRows);
  `, context);

  assert.equal(context.result.previousLabel, '5月');
  assert.equal(context.result.previousRatio, 0.4);
  assert.equal(context.result.change, 0.4);
});

test('较上月不使用周周期数据', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = '7';
    state.compareDimension = '周';
    state.runtime = {
      reports: [{
        id: 'conversion',
        numeratorField: '新增客户数_SCRM',
        denominatorField: '新登账号_GDATA',
        rows: [
          { '周期类型': '周', '统计周期': '5.25-5.31', '开始日期': '2026-05-25', '结束日期': '2026-05-31', '新增客户数_SCRM': 10, '新登账号_GDATA': 100 },
          { '周期类型': '月', '统计周期': '5月', '开始日期': '2026-05-01', '结束日期': '2026-05-31', '新增客户数_SCRM': 40, '新登账号_GDATA': 100 },
          { '周期类型': '周', '统计周期': '6.22-6.28', '开始日期': '2026-06-22', '结束日期': '2026-06-28', '新增客户数_SCRM': 80, '新登账号_GDATA': 100 }
        ]
      }]
    };
    const report = state.runtime.reports[0];
    const currentRows = rowsFor(report);
    globalThis.result = previousMonthChange(report, currentRows);
  `, context);

  assert.equal(context.result.previousLabel, '5月');
  assert.equal(context.result.previousRatio, 0.4);
  assert.equal(context.result.change, 0.4);
});

test('日维度不展示环比对比卡片', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = 'custom';
    state.customStart = '2026-06-30';
    state.customEnd = '2026-06-30';
    state.compareDimension = '日';
    state.runtime = {
      reports: [{
        id: 'conversion',
        numeratorField: '新增客户数_SCRM',
        denominatorField: '新登账号_GDATA',
        rows: [
          { '周期类型': '日', '统计周期': '2026-05-31', '开始日期': '2026-05-31', '结束日期': '2026-05-31', '新增客户数_SCRM': 10, '新登账号_GDATA': 100 },
          { '周期类型': '月', '统计周期': '5月', '开始日期': '2026-05-01', '结束日期': '2026-05-31', '新增客户数_SCRM': 90, '新登账号_GDATA': 100 },
          { '周期类型': '日', '统计周期': '2026-06-30', '开始日期': '2026-06-30', '结束日期': '2026-06-30', '新增客户数_SCRM': 50, '新登账号_GDATA': 100 }
        ]
      }]
    };
    const report = state.runtime.reports[0];
    const currentRows = rowsFor(report);
    globalThis.cards = comparisonCards(report, currentRows);
  `, context);

  assert.equal(context.cards.length, 0);
});

test('周维度只展示较上周和较上月数据对比', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = 'custom';
    state.customStart = '2026-06-22';
    state.customEnd = '2026-06-28';
    state.compareDimension = '周';
    state.runtime = {
      reports: [{
        id: 'conversion',
        numeratorField: '新增客户数_SCRM',
        denominatorField: '新登账号_GDATA',
        rows: [
          { '周期类型': '周', '统计周期': '5.25-5.31', '开始日期': '2026-05-25', '结束日期': '2026-05-31', '新增客户数_SCRM': 20, '新登账号_GDATA': 100 },
          { '周期类型': '月', '统计周期': '5月', '开始日期': '2026-05-01', '结束日期': '2026-05-31', '新增客户数_SCRM': 40, '新登账号_GDATA': 100 },
          { '周期类型': '周', '统计周期': '6.22-6.28', '开始日期': '2026-06-22', '结束日期': '2026-06-28', '新增客户数_SCRM': 80, '新登账号_GDATA': 100 }
        ]
      }]
    };
    const report = state.runtime.reports[0];
    const currentRows = rowsFor(report);
    globalThis.cards = comparisonCards(report, currentRows);
  `, context);

  assert.equal(context.cards.length, 2);
  assert.equal(context.cards[0].label, '较上周变化');
  assert.equal(context.cards[1].label, '较上月变化');
  assert.match(context.cards[1].hint, /上月 5月：40.00%/);
});

test('新登账号数和新增客户数不渲染冗余说明', () => {
  const context = loadAppContext();
  vm.runInContext(`
    state.range = 'custom';
    state.customStart = '2026-06-30';
    state.customEnd = '2026-06-30';
    state.compareDimension = '日';
    const report = {
      id: 'conversion',
      numeratorField: '新增客户数_SCRM',
      denominatorField: '新登账号_GDATA',
      ratioField: '新用户转化率',
      rows: [
        { '周期类型': '日', '统计周期': '2026-06-30', '开始日期': '2026-06-30', '结束日期': '2026-06-30', '新增客户数_SCRM': 50, '新登账号_GDATA': 100, '新用户转化率': '50.00%' }
      ]
    };
    renderKpis(report);
  `, context);

  const html = context.__elements['#kpiGrid'].innerHTML;
  assert.match(html, /新登账号数/);
  assert.match(html, /新增客户数/);
  assert.doesNotMatch(html, /当前筛选范围内新登账号/);
  assert.doesNotMatch(html, /当前筛选范围内新增客户数/);
  assert.match(html, /新增客户数 \/ 新登账号数/);
});

test('同步预览文案包含两张报表的日周月行数', () => {
  const context = loadAppContext();
  vm.runInContext(`
    const syncReportsFixture = [
      {
        title: '新用户转化率',
        rows: [{ '周期类型': '日' }, { '周期类型': '周' }, { '周期类型': '月' }]
      },
      {
        title: '活跃用户关注私域占比',
        rows: [{ '周期类型': '日' }, { '周期类型': '日' }]
      }
    ];
    globalThis.previewText = syncPreviewText(syncReportsFixture);
  `, context);

  assert.match(context.previewText, /预计同步 5 行/);
  assert.match(context.previewText, /新用户转化率：共 3 行（日 1 \/ 周 1 \/ 月 1）/);
  assert.match(context.previewText, /活跃用户关注私域占比：共 2 行（日 2 \/ 周 0 \/ 月 0）/);
});
