const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('页面提供日周月对比维度入口', () => {
  const html = fs.readFileSync(path.resolve(__dirname, '../static/index.html'), 'utf8');

  assert.match(html, /data-dimension="日"/);
  assert.match(html, /data-dimension="周"/);
  assert.match(html, /data-dimension="月"/);
});

function createElement() {
  return {
    classList: { toggle() {}, add() {}, remove() {} },
    dataset: {},
    disabled: false,
    innerHTML: '',
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
  const source = fs.readFileSync(appPath, 'utf8').replace(/\nbindEvents\(\);\s*load\(\)\.catch[\s\S]*$/, '');
  const elements = {};
  const context = {
    Blob: function Blob() {},
    URL: { createObjectURL() { return ''; }, revokeObjectURL() {} },
    document: {
      body: { classList: { toggle() {} }, appendChild() {} },
      createElement,
      getElementById(id) {
        elements[id] ||= createElement();
        return elements[id];
      },
      querySelector() { return createElement(); },
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

test('日维度按批次日期逐日展示趋势周期', () => {
  const context = loadAppContext();
  vm.runInContext(`
    const batches = [
      {
        batch: '6月01日',
        date: '2026-06-01',
        experiment: { '用户量': 100, 'LTV7': '2.00', '次日留存率': '20.00%', '大盘次日留存率': '18.00%' },
        control: { '用户量': 100, 'LTV7': '1.00', '次日留存率': '10.00%' }
      },
      {
        batch: '6月02日',
        date: '2026-06-02',
        experiment: { '用户量': 100, 'LTV7': '4.00', '次日留存率': '40.00%', '大盘次日留存率': '30.00%' },
        control: { '用户量': 100, 'LTV7': '3.00', '次日留存率': '30.00%' }
      }
    ];
    const periods = periodRows(batches, '日');
    globalThis.labels = JSON.stringify(periods.map((item) => item.batch));
    globalThis.keys = JSON.stringify(periods.map((item) => item.key));
    globalThis.ltv = JSON.stringify(periods.map((item) => item.experiment.LTV7));
  `, context);

  assert.equal(context.labels, '["6.1","6.2"]');
  assert.equal(context.keys, '["2026-06-01","2026-06-02"]');
  assert.equal(context.ltv, '["2.00","4.00"]');
});
