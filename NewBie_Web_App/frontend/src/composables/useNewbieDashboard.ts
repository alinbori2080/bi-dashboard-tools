// @ts-nocheck
// 新锐攻略看板业务逻辑：从旧静态脚本迁移到前端工程源码。

let mounted = false;

export function mountNewbieDashboard() {
  if (mounted) return;
  mounted = true;
const state = {
  status: null,
  runtime: null,
  range: "all",
  customStart: "",
  customEnd: "",
  compareDimension: "日",
  ltvMetric: "LTV7",
  retentionMetric: "次日留存率",
  sourceMode: "feishu",
  sidePanelCollapsed: localStorage.getItem("newbieSidePanelCollapsed") !== "false",
};

const els = {
  pathLine: document.getElementById("pathLine"),
  menuButton: document.getElementById("menuButton"),
  sidePanelButton: document.getElementById("sidePanelButton"),
  refreshBtn: document.getElementById("refreshBtn"),
  syncBtn: document.getElementById("syncBtn"),
  exportBtn: document.getElementById("exportBtn"),
  statusBanner: document.getElementById("statusBanner"),
  sourceModeButtons: document.getElementById("sourceModeButtons"),
  rangeButtons: document.getElementById("rangeButtons"),
  compareButtons: document.getElementById("compareButtons"),
  ltvMetricButtons: document.getElementById("ltvMetricButtons"),
  retentionMetricButtons: document.getElementById("retentionMetricButtons"),
  customRange: document.getElementById("customRange"),
  startDate: document.getElementById("startDate"),
  endDate: document.getElementById("endDate"),
  sourceList: document.getElementById("sourceList"),
  syncInfo: document.getElementById("syncInfo"),
  errorPanel: document.getElementById("errorPanel"),
  lastRefresh: document.getElementById("lastRefresh"),
  kpiGrid: document.getElementById("kpiGrid"),
  kpiPeriod: document.getElementById("kpiPeriod"),
  ltvSubtitle: document.getElementById("ltvSubtitle"),
  retentionSubtitle: document.getElementById("retentionSubtitle"),
  ltvChart: document.getElementById("ltvChart"),
  retentionChart: document.getElementById("retentionChart"),
  rowCount: document.getElementById("rowCount"),
  tableHead: document.getElementById("tableHead"),
  tableBody: document.getElementById("tableBody"),
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function exportTimestamp(date = new Date()) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}_${pad2(date.getHours())}点${pad2(date.getMinutes())}分`;
}

function safeFilePart(value) {
  return String(value || "report")
    .trim()
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
    .replace(/\s+/g, " ")
    .slice(0, 80) || "report";
}

function nextExportFilename(reportTitle, extension) {
  const base = `${safeFilePart(reportTitle)}_${exportTimestamp()}`;
  const key = `newbie-export-${base}.${extension}`;
  const count = Number(localStorage.getItem(key) || "0") + 1;
  localStorage.setItem(key, String(count));
  const suffix = count === 1 ? "" : `_${pad2(count)}`;
  return `${base}${suffix}.${extension}`;
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function csvText(columns, data) {
  const lines = [
    columns.map(csvCell).join(","),
    ...data.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
  ];
  return `\ufeff${lines.join("\r\n")}`;
}

function downloadText(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatSigned(value, suffix = "") {
  if (value == null || !Number.isFinite(value)) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}${suffix}`;
}

function parsePercent(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  return Number(text.replace("%", "")) / 100;
}

function parseMetric(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  const parsed = Number(text.split("（")[0].replaceAll(",", ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function signedClass(value) {
  const text = String(value || "").trim();
  const number = text.endsWith("%") ? parsePercent(text) : parseMetric(text.replace("pp", ""));
  if (number == null || number === 0) return "";
  return number > 0 ? "positive" : "negative";
}

function report() {
  return (state.runtime?.reports || [])[0] || null;
}

function rows() {
  return report()?.rows || [];
}

function fieldnames() {
  return report()?.fieldnames || [];
}

function batchRows() {
  const result = [];
  let current = null;
  for (const row of rows()) {
    const batch = String(row["批次"] || "").trim();
    if (batch) {
      current = {
        batch,
        date: row["批次日期"] || "",
        experiment: row,
        control: null,
      };
      result.push(current);
    } else if (current) {
      current.control = row;
    }
  }
  return result;
}

function latestDate(batches) {
  const dates = batches.map((item) => item.date).filter(Boolean).sort();
  return dates.length ? dates[dates.length - 1] : "";
}

function selectedDateRange(batches) {
  const end = latestDate(batches);
  if (!end) return { start: "", end: "" };
  if (state.range === "all") return { start: "", end: "" };
  if (state.range === "custom") return { start: state.customStart, end: state.customEnd };
  const endDate = new Date(`${end}T00:00:00`);
  endDate.setDate(endDate.getDate() - Number(state.range) + 1);
  return { start: isoDate(endDate), end };
}

function filteredBatches() {
  const batches = batchRows();
  const range = selectedDateRange(batches);
  return batches.filter((item) => {
    if (!item.date) return true;
    if (range.start && item.date < range.start) return false;
    if (range.end && item.date > range.end) return false;
    return true;
  });
}

function filteredRows() {
  return filteredBatches().flatMap((item) => [item.experiment, item.control].filter(Boolean));
}

function displayRows() {
  return filteredBatches()
    .slice()
    .sort((left, right) => String(right.date || "").localeCompare(String(left.date || "")))
    .flatMap((item) => [item.experiment, item.control].filter(Boolean));
}

function monthStart(dateValue) {
  return `${dateValue.slice(0, 7)}-01`;
}

function labelDate(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  return `${date.getMonth() + 1}.${date.getDate()}`;
}

function weekStartKey(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  const offset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - offset);
  return isoDate(date);
}

function periodLabel(key, items) {
  const dated = items.map((item) => item.date).filter(Boolean).sort();
  if (!dated.length) return key;
  const start = labelDate(dated[0]);
  const end = labelDate(dated[dated.length - 1]);
  return start === end ? start : `${start}-${end}`;
}

function weightedMetric(items, group, field) {
  let totalUsers = 0;
  let totalValue = 0;
  for (const item of items) {
    const row = item[group];
    const users = Number(row?.["用户量"] || 0);
    const value = parseMetric(row?.[field]);
    if (!users || value == null) continue;
    totalUsers += users;
    totalValue += value * users;
  }
  return totalUsers ? totalValue / totalUsers : null;
}

function weightedPercent(items, group, field) {
  let totalUsers = 0;
  let totalValue = 0;
  for (const item of items) {
    const row = item[group];
    const users = Number(row?.["用户量"] || 0);
    const value = parsePercent(row?.[field]);
    if (!users || value == null) continue;
    totalUsers += users;
    totalValue += value * users;
  }
  return totalUsers ? totalValue / totalUsers : null;
}

function periodRows(sourceBatches = filteredBatches(), dimension = state.compareDimension) {
  const grouped = new Map();
  const batches = [...sourceBatches].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  if (dimension === "日") {
    for (const batch of batches) {
      const key = batch.date || batch.batch;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(batch);
    }
  } else if (dimension === "周") {
    for (const batch of batches) {
      const key = batch.date ? weekStartKey(batch.date) : batch.batch;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(batch);
    }
  } else {
    for (const batch of batches) {
      const key = batch.date ? monthStart(batch.date) : batch.batch;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(batch);
    }
  }
  return [...grouped.entries()].map(([key, items]) => {
    const experimentUsers = items.reduce((sum, item) => sum + Number(item.experiment?.["用户量"] || 0), 0);
    const controlUsers = items.reduce((sum, item) => sum + Number(item.control?.["用户量"] || 0), 0);
    const period = {
      key,
      batch: periodLabel(key, items),
      date: items[items.length - 1]?.date || key,
      sourceCount: items.length,
      experimentUsers,
      controlUsers,
      experiment: { "用户量": experimentUsers },
      control: { "用户量": controlUsers },
    };
    for (const field of ["LTV7", "LTV15", "LTV30"]) {
      const expValue = weightedMetric(items, "experiment", field);
      const controlValue = weightedMetric(items, "control", field);
      period.experiment[field] = expValue == null ? "" : expValue.toFixed(2);
      period.control[field] = controlValue == null ? "" : controlValue.toFixed(2);
      period.experiment[`${field}差值`] = expValue == null || controlValue == null ? "" : (expValue - controlValue).toFixed(2);
    }
    for (const field of ["次日留存率", "3日留存率", "7日留存率"]) {
      const expValue = weightedPercent(items, "experiment", field);
      const controlValue = weightedPercent(items, "control", field);
      const marketValue = weightedPercent(items, "experiment", `大盘${field}`);
      period.experiment[field] = expValue == null ? "" : `${(expValue * 100).toFixed(2)}%`;
      period.control[field] = controlValue == null ? "" : `${(controlValue * 100).toFixed(2)}%`;
      period.experiment[`大盘${field}`] = marketValue == null ? "" : `${(marketValue * 100).toFixed(2)}%`;
    }
    return period;
  });
}

function comparisonPeriodRows(sourceBatches = filteredBatches()) {
  return periodRows(sourceBatches, "周");
}

function lastRefreshText(status = state.status || {}) {
  return `最后刷新：${status.lastRefresh || "未刷新"}`;
}

function feishuStatusMessage(sync, errors, config) {
  if (errors.length) return sync.message || errors[0]?.body || "本次刷新失败。";
  if (!config.ready) return config.message || "飞书配置异常。";
  if (state.sourceMode === "feishu" || sync.sourceMode === "feishu") {
    return "飞书结果表当前数据已来自飞书结果表，无需同步。";
  }
  return sync.message || "尚未同步";
}

function feishuStatusClass(sync, errors, config) {
  if (errors.length || !config.ready) return "error";
  if (state.sourceMode === "feishu" || sync.sourceMode === "feishu") return "neutral";
  if (sync.ok) return "success";
  if (sync.ready) return "warning";
  if (sync.blocked) return "error";
  if (sync.message && sync.message !== "尚未刷新") return "error";
  return "neutral";
}

function renderStatus() {
  const status = state.status || {};
  const sync = status.lastSync || {};
  const config = status.config || {};
  const errors = state.runtime?.errors || [];
  els.sourceModeButtons.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("selected", button.dataset.sourceMode === state.sourceMode);
  });
  els.pathLine.textContent = state.sourceMode === "feishu" ? "飞书结果表" : (status.dataDir || "");
  els.lastRefresh.textContent = lastRefreshText(status);
  els.statusBanner.textContent = feishuStatusMessage(sync, errors, config);
  els.statusBanner.className = `status-banner ${feishuStatusClass(sync, errors, config)}`;
  els.syncBtn.disabled = state.sourceMode === "feishu" || Boolean(sync.blocked) || !(state.runtime?.reports || []).length;
  els.exportBtn.disabled = !(state.runtime?.reports || []).length;
}

function renderSources() {
  const reportSources = report()?.sources || [];
  const sources = (state.sourceMode === "feishu" ? reportSources : (state.status?.sources || []))
    .filter((source) => !String(source.name || "").startsWith("."));
  if (!sources.length) {
    els.sourceList.innerHTML = `<div class="empty">${state.sourceMode === "feishu" ? "尚未读取飞书结果表" : "data 目录暂无源文件"}</div>`;
    return;
  }
  els.sourceList.innerHTML = sources.map((source) => `
    <article class="source-row">
      <strong>${escapeHtml(source.name)}</strong>
      <span>${escapeHtml(source.role)} · ${escapeHtml(source.updatedAt)}</span>
    </article>
  `).join("");
}

function renderSyncInfo() {
  const config = state.status?.config || {};
  const sync = state.status?.lastSync || {};
  const errors = state.runtime?.errors || [];
  const rows = [
    ["数据源", state.sourceMode === "feishu" ? "飞书结果表" : "本地文件"],
    ["配置", config.ready ? "可用" : (config.message || "不可用")],
    ["飞书状态", feishuStatusMessage(sync, errors, config)],
    ["新增", sync.created ?? "-"],
    ["更新", sync.updated ?? "-"],
  ];
  if (config.appUrl) {
    rows.push(["飞书链接", `<a href="${escapeHtml(config.appUrl)}" target="_blank" rel="noreferrer">打开</a>`]);
  }
  els.syncInfo.innerHTML = rows.map(([label, value]) => `
    <dt>${escapeHtml(label)}</dt>
    <dd>${String(value).startsWith("<a ") ? value : escapeHtml(value)}</dd>
  `).join("");
}

function renderErrors() {
  const errors = state.runtime?.errors || [];
  if (!errors.length) {
    els.errorPanel.classList.add("hidden");
    els.errorPanel.innerHTML = "";
    return;
  }
  els.errorPanel.classList.remove("hidden");
  els.errorPanel.innerHTML = errors.map((error) => `
    <h3>${escapeHtml(error.title || "计算失败")}</h3>
    <p>${escapeHtml(error.body || "")}</p>
  `).join("");
}

function retentionDiff(batch, field) {
  const left = parsePercent(batch.experiment?.[field]);
  const right = parsePercent(batch.control?.[field]);
  if (left == null || right == null) return "";
  return `${((left - right) * 100).toFixed(2)}%`;
}

function retentionDiffNumber(batch, field) {
  const left = parsePercent(batch?.experiment?.[field]);
  const right = parsePercent(batch?.control?.[field]);
  if (left == null || right == null) return null;
  return (left - right) * 100;
}

function isoDate(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function addDaysToIso(value, days) {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

function addMonthsToIso(value, months) {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00`);
  const targetMonth = date.getMonth() + months;
  const lastDay = new Date(date.getFullYear(), targetMonth + 1, 0).getDate();
  return isoDate(new Date(date.getFullYear(), targetMonth, Math.min(date.getDate(), lastDay)));
}

function dateRangeFromBatches(batches) {
  const dates = batches.map((item) => item.date).filter(Boolean).sort();
  if (!dates.length) return null;
  return { start: dates[0], end: dates[dates.length - 1] };
}

function renderKpiPeriod(batches) {
  if (!els.kpiPeriod) return;
  const dates = batches.map((item) => item.date).filter(Boolean).sort();
  if (!dates.length) {
    els.kpiPeriod.textContent = '当前统计批次：当前筛选下无可统计批次';
    return;
  }
  const batchText = dates.length <= 4
    ? dates.join('、')
    : `${dates[0]} 至 ${dates[dates.length - 1]}（${dates.length} 个批次）`;
  els.kpiPeriod.textContent = `当前统计批次：${batchText}`;
}

function batchesInRange(sourceBatches, range) {
  if (!range) return [];
  return sourceBatches.filter((item) => item.date && item.date >= range.start && item.date <= range.end);
}

function comparisonDateRange(currentBatches) {
  if (state.range === "all") {
    return null;
  }
  const selectedRange = selectedDateRange(batchRows());
  if (selectedRange?.start && selectedRange?.end) {
    return selectedRange;
  }
  return dateRangeFromBatches(currentBatches);
}

function shiftedRange(currentBatches, shiftStart, shiftEnd) {
  const range = comparisonDateRange(currentBatches);
  if (!range) return null;
  return { start: shiftStart(range.start), end: shiftEnd(range.end) };
}

function shiftedBatches(currentBatches, shiftStart, shiftEnd) {
  const range = shiftedRange(currentBatches, shiftStart, shiftEnd);
  return range ? batchesInRange(batchRows(), range) : [];
}

function previousMonthRange(currentBatches) {
  return state.compareDimension === "月"
    ? shiftedRange(currentBatches, (date) => addMonthsToIso(date, -1), (date) => addMonthsToIso(date, -1))
    : shiftedRange(currentBatches, (date) => addDaysToIso(date, -28), (date) => addDaysToIso(date, -28));
}

function previousMonthLabel() {
  return state.compareDimension === "月" ? "上月" : "4周前";
}

function isoRangeLabel(range) {
  if (!range?.start || !range?.end) return '';
  const start = labelDate(range.start);
  const end = labelDate(range.end);
  return start === end ? start : `${start}-${end}`;
}

function ltvDiffValue(batches, field) {
  const baseField = field.replace("差值", "");
  const experimentValue = weightedMetric(batches, "experiment", baseField);
  const controlValue = weightedMetric(batches, "control", baseField);
  return experimentValue == null || controlValue == null ? null : experimentValue - controlValue;
}

function percentText(value) {
  return value == null || !Number.isFinite(value) ? "-" : `${(value * 100).toFixed(2)}%`;
}

function metricChange(currentBatches, previousBatches, field, kind, meta = {}) {
  if (state.range === "all") {
    return {
      delta: "-",
      previous: "-",
      hint: "全部范围不支持环比",
      prefix: "全部范围不支持环比",
    };
  }
  const currentValue = kind === "retention"
    ? (weightedPercent(currentBatches, "experiment", field) == null ? null : weightedPercent(currentBatches, "experiment", field) * 100)
    : ltvDiffValue(currentBatches, field);
  const previousValue = kind === "retention"
    ? (weightedPercent(previousBatches, "experiment", field) == null ? null : weightedPercent(previousBatches, "experiment", field) * 100)
    : ltvDiffValue(previousBatches, field);
  const suffix = kind === "retention" ? "pp" : "";
  const previousText = previousValue == null ? "-" : `${previousValue.toFixed(2)}${suffix}`;
  const rangeText = isoRangeLabel(meta.range);
  if (currentValue == null || previousValue == null) {
    return {
      delta: "-",
      previous: previousText,
      hint: rangeText ? `${meta.label} ${rangeText}：-` : `${meta.label}：-`,
      prefix: rangeText ? `${meta.label} ${rangeText}：` : `${meta.label}：`,
    };
  }
  const delta = formatSigned(currentValue - previousValue, suffix);
  return {
    delta,
    previous: previousText,
    hint: rangeText ? `${meta.label} ${rangeText}：${delta}` : `${meta.label}：${delta}`,
    prefix: rangeText ? `${meta.label} ${rangeText}：` : `${meta.label}：`,
  };
}

function ltvCard(label, currentBatches, previousWeekBatches, previousMonthBatches, field, weekMeta, monthMeta) {
  const value = ltvDiffValue(currentBatches, field);
  return {
    label,
    value: value == null ? "-" : value.toFixed(2),
    tone: signedClass(value),
    week: metricChange(currentBatches, previousWeekBatches, field, "ltv", weekMeta),
    month: metricChange(currentBatches, previousMonthBatches, field, "ltv", monthMeta),
    type: "ltv",
  };
}

function retentionCompare(batches, field, target) {
  const current = weightedPercent(batches, "experiment", field);
  const other = target === "control"
    ? weightedPercent(batches, "control", field)
    : weightedPercent(batches, "experiment", `大盘${field}`);
  if (current == null || other == null) return "-";
  return formatSigned((current - other) * 100, "pp");
}

function retentionCard(label, batches, field) {
  return {
    label,
    value: percentText(weightedPercent(batches, "experiment", field)),
    control: retentionCompare(batches, field, "control"),
    market: retentionCompare(batches, field, "market"),
    type: "retention",
  };
}

function renderKpis() {
  const currentBatches = filteredBatches();
  renderKpiPeriod(currentBatches);
  const previousWeekRange = shiftedRange(currentBatches, (date) => addDaysToIso(date, -7), (date) => addDaysToIso(date, -7));
  const monthRange = previousMonthRange(currentBatches);
  const previousWeekBatches = previousWeekRange ? batchesInRange(batchRows(), previousWeekRange) : [];
  const previousMonthBatches = monthRange ? batchesInRange(batchRows(), monthRange) : [];
  const monthLabel = previousMonthLabel();
  const experimentUsers = currentBatches.reduce((sum, item) => sum + Number(item.experiment?.["用户量"] || 0), 0);
  const controlUsers = currentBatches.reduce((sum, item) => sum + Number(item.control?.["用户量"] || 0), 0);
  const items = [
    { label: "用户量", experimentUsers, controlUsers, type: "users" },
    ltvCard("LTV7差值", currentBatches, previousWeekBatches, previousMonthBatches, "LTV7差值", { label: "上周", range: previousWeekRange }, { label: monthLabel, range: monthRange }),
    ltvCard("LTV15差值", currentBatches, previousWeekBatches, previousMonthBatches, "LTV15差值", { label: "上周", range: previousWeekRange }, { label: monthLabel, range: monthRange }),
    ltvCard("LTV30差值", currentBatches, previousWeekBatches, previousMonthBatches, "LTV30差值", { label: "上周", range: previousWeekRange }, { label: monthLabel, range: monthRange }),
    retentionCard("实验组次日留存", currentBatches, "次日留存率"),
    retentionCard("实验组3日留存", currentBatches, "3日留存率"),
    retentionCard("实验组7日留存", currentBatches, "7日留存率"),
  ];
  els.kpiGrid.innerHTML = items.map((item) => `
    <article class="kpi-card">
      <small>${escapeHtml(item.label)}</small>
      ${item.type === "users" ? `
        <div class="user-split">
          <div><span>实验组</span><strong>${escapeHtml(formatNumber(item.experimentUsers))}</strong></div>
          <div><span>对照组</span><strong>${escapeHtml(formatNumber(item.controlUsers))}</strong></div>
        </div>
      ` : `
        <strong class="${item.tone || ""}">${escapeHtml(item.value)}</strong>
      `}
      ${item.type === "ltv" ? `<div class="delta-line">
        <small>${escapeHtml(item.week.prefix || '')}<span class="${signedClass(item.week.delta)}">${escapeHtml(item.week.delta)}</span></small>
      </div>
      <div class="delta-line">
        <small>${escapeHtml(item.month.prefix || '')}<span class="${signedClass(item.month.delta)}">${escapeHtml(item.month.delta)}</span></small>
      </div>` : ""}
      ${item.type === "retention" ? `<div class="delta-line">
        <small>较对照组 <span class="${signedClass(item.control)}">${escapeHtml(item.control)}</span></small>
      </div>
      <div class="delta-line">
        <small>较大盘 <span class="${signedClass(item.market)}">${escapeHtml(item.market)}</span></small>
      </div>` : ""}
    </article>
  `).join("");
}

function chartScales(series, height, padding) {
  const values = series.flat().filter((value) => value != null && Number.isFinite(value));
  if (!values.length) return { min: 0, max: 1 };
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min = Math.min(0, min);
    max = max + 1;
  }
  const pad = (max - min) * 0.12;
  return { min: min - pad, max: max + pad };
}

function polyline(points) {
  return points.filter((point) => point.value != null).map((point) => `${point.x},${point.y}`).join(" ");
}

function renderLtvChart() {
  const periods = periodRows();
  els.ltvSubtitle.textContent = periods.length ? `${state.ltvMetric} · 按${state.compareDimension}展示 ${periods.length} 个周期` : `当前筛选下无${state.compareDimension}数据`;
  if (!periods.length) {
    els.ltvChart.innerHTML = '<div class="empty">没有可绘制的数据</div>';
    return;
  }
  const height = 320;
  const padding = { top: 44, right: 40, bottom: 54, left: 64 };
  const width = Math.max(920, padding.left + padding.right + periods.length * 110);
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const band = innerWidth / periods.length;
  const diffField = `${state.ltvMetric}差值`;
  const exp = periods.map((item) => parseMetric(item.experiment?.[state.ltvMetric]));
  const control = periods.map((item) => parseMetric(item.control?.[state.ltvMetric]));
  const diff = periods.map((item) => parseMetric(item.experiment?.[diffField]));
  const { min, max } = chartScales([exp, control, diff], height, padding);
  const x = (index) => padding.left + index * band + band / 2;
  const y = (value) => padding.top + innerHeight - ((value - min) / (max - min)) * innerHeight;
  const zeroY = y(0);
  const barWidth = Math.min(24, band / 3);
  const grid = [0, 0.25, 0.5, 0.75, 1].map((tick) => {
    const gy = padding.top + innerHeight * tick;
    const label = (max - (max - min) * tick).toFixed(1);
    return `<line x1="${padding.left}" y1="${gy}" x2="${width - padding.right}" y2="${gy}" class="grid-line" />
      <text x="${padding.left - 10}" y="${gy + 4}" text-anchor="end" class="axis-label">${label}</text>`;
  }).join("");
    const bars = diff.map((value, index) => {
      if (value == null) return "";
      const top = Math.min(y(value), zeroY);
      const heightValue = Math.abs(zeroY - y(value));
      return `<rect x="${x(index) - barWidth / 2}" y="${top}" width="${barWidth}" height="${heightValue}" rx="3" class="bar amber" />`;
    }).join("");
  const expPoints = exp.map((value, index) => ({ value, x: x(index), y: value == null ? 0 : y(value) }));
  const controlPoints = control.map((value, index) => ({ value, x: x(index), y: value == null ? 0 : y(value) }));
    const diffLabels = diff.map((value, index) => {
      if (value == null) return "";
      const labelY = value >= 0 ? Math.max(padding.top + 8, y(value) - 6) : Math.min(padding.top + innerHeight - 4, y(value) + 14);
      return `<text x="${x(index)}" y="${labelY}" text-anchor="middle" class="diff-label">${escapeHtml(value.toFixed(2))}</text>`;
    }).join("");
    const expValueLabels = expPoints.map((point) => point.value == null ? "" : `
      <text x="${point.x}" y="${Math.max(padding.top + 8, point.y - 10)}" text-anchor="middle" class="chart-label">${point.value.toFixed(2)}</text>
    `).join("");
    const controlValueLabels = controlPoints.map((point) => point.value == null ? "" : `
      <text x="${point.x}" y="${Math.min(padding.top + innerHeight - 4, point.y + 16)}" text-anchor="middle" class="chart-label">${point.value.toFixed(2)}</text>
    `).join("");
    const labels = periods.map((item, index) => `
      <text x="${x(index)}" y="${height - 20}" text-anchor="middle" class="axis-label">${escapeHtml(item.batch)}</text>
    `).join("");
    els.ltvChart.innerHTML = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
      ${grid}
      <line x1="${padding.left}" y1="${zeroY}" x2="${width - padding.right}" y2="${zeroY}" class="zero-line" />
      ${bars}
      <polyline points="${polyline(expPoints)}" class="line blue" />
      <polyline points="${polyline(controlPoints)}" class="line teal" />
      ${expPoints.map((point) => point.value == null ? "" : `<circle cx="${point.x}" cy="${point.y}" r="3.5" class="dot blue" />`).join("")}
      ${controlPoints.map((point) => point.value == null ? "" : `<circle cx="${point.x}" cy="${point.y}" r="3.5" class="dot teal" />`).join("")}
      ${diffLabels}
      ${expValueLabels}
      ${controlValueLabels}
    <line x1="${padding.left}" y1="${padding.top + innerHeight}" x2="${width - padding.right}" y2="${padding.top + innerHeight}" class="axis-line" />
    ${labels}
  </svg>`;
}

function renderRetentionChart() {
  const periods = periodRows();
  const marketField = `大盘${state.retentionMetric}`;
  els.retentionSubtitle.textContent = periods.length ? `${state.retentionMetric} · 按${state.compareDimension}展示 ${periods.length} 个周期` : `当前筛选下无${state.compareDimension}数据`;
  if (!periods.length) {
    els.retentionChart.innerHTML = '<div class="empty">没有可绘制的数据</div>';
    return;
  }
  const height = 320;
  const padding = { top: 44, right: 40, bottom: 54, left: 64 };
  const width = Math.max(920, padding.left + padding.right + periods.length * 110);
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const band = innerWidth / periods.length;
  const exp = periods.map((item) => parsePercent(item.experiment?.[state.retentionMetric]));
  const control = periods.map((item) => parsePercent(item.control?.[state.retentionMetric]));
  const market = periods.map((item) => parsePercent(item.experiment?.[marketField]));
  const allValues = [...exp, ...control, ...market].filter((value) => value != null && Number.isFinite(value));
  let min = allValues.length ? Math.min(...allValues) : 0;
  let max = allValues.length ? Math.max(...allValues) : 0.01;
  if (min === max) {
    min = Math.max(0, min - 0.05);
    max = Math.min(1, max + 0.05);
  }
  const pad = Math.max((max - min) * 0.18, 0.015);
  min = Math.max(0, min - pad);
  max = Math.min(1, max + pad);
  const x = (index) => padding.left + index * band + band / 2;
  const y = (value) => padding.top + innerHeight - ((value - min) / (max - min)) * innerHeight;
  const grid = [0, 0.25, 0.5, 0.75, 1].map((tick) => {
    const gy = padding.top + innerHeight * tick;
    const label = `${((max - (max - min) * tick) * 100).toFixed(0)}%`;
    return `<line x1="${padding.left}" y1="${gy}" x2="${width - padding.right}" y2="${gy}" class="grid-line" />
      <text x="${padding.left - 10}" y="${gy + 4}" text-anchor="end" class="axis-label">${label}</text>`;
  }).join("");
  const pointsFor = (series) => series.map((value, index) => ({ value, x: x(index), y: value == null ? 0 : y(value) }));
  const expPoints = pointsFor(exp);
  const controlPoints = pointsFor(control);
  const marketPoints = pointsFor(market);
  const percentLabel = (value) => `${(value * 100).toFixed(2)}%`;
    const expValueLabels = expPoints.map((point) => point.value == null ? "" : `
      <text x="${point.x}" y="${Math.max(padding.top + 10, point.y - 18)}" text-anchor="middle" class="chart-label chart-label-blue">${percentLabel(point.value)}</text>
    `).join("");
    const controlValueLabels = controlPoints.map((point) => point.value == null ? "" : `
      <text x="${point.x}" y="${Math.min(padding.top + innerHeight - 6, point.y + 18)}" text-anchor="middle" class="chart-label chart-label-teal">${percentLabel(point.value)}</text>
    `).join("");
    const marketValueLabels = marketPoints.map((point) => point.value == null ? "" : `
      <text x="${point.x}" y="${Math.max(padding.top + 10, point.y - 34)}" text-anchor="middle" class="chart-label chart-label-gray">${percentLabel(point.value)}</text>
    `).join("");
    const labels = periods.map((item, index) => `
      <text x="${x(index)}" y="${height - 20}" text-anchor="middle" class="axis-label">${escapeHtml(item.batch)}</text>
    `).join("");
    els.retentionChart.innerHTML = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
      ${grid}
      <polyline points="${polyline(expPoints)}" class="line blue" />
      <polyline points="${polyline(controlPoints)}" class="line teal" />
      <polyline points="${polyline(marketPoints)}" class="line gray" />
      ${expPoints.map((point) => point.value == null ? "" : `<circle cx="${point.x}" cy="${point.y}" r="3.5" class="dot blue" />`).join("")}
      ${controlPoints.map((point) => point.value == null ? "" : `<circle cx="${point.x}" cy="${point.y}" r="3.5" class="dot teal" />`).join("")}
      ${marketPoints.map((point) => point.value == null ? "" : `<circle cx="${point.x}" cy="${point.y}" r="3.5" class="dot gray" />`).join("")}
      ${expValueLabels}
      ${controlValueLabels}
      ${marketValueLabels}
    <line x1="${padding.left}" y1="${padding.top + innerHeight}" x2="${width - padding.right}" y2="${padding.top + innerHeight}" class="axis-line" />
    ${labels}
  </svg>`;
}

function renderTable() {
  const displayFields = fieldnames();
  const data = displayRows();
  els.rowCount.textContent = `${data.length} 条`;
  els.tableHead.innerHTML = displayFields.length ? `<tr>${displayFields.map((field) => `<th>${escapeHtml(field)}</th>`).join("")}</tr>` : "";
  els.tableBody.innerHTML = data.map((row) => `
    <tr>${displayFields.map((field) => `<td>${escapeHtml(row[field] ?? "")}</td>`).join("")}</tr>
  `).join("");
}

function exportCurrentReport() {
  const currentReport = report();
  const displayFields = fieldnames();
  if (!currentReport || !displayFields.length) {
    window.alert("没有可导出的报表，请先刷新数据。");
    return;
  }
  const filename = nextExportFilename(currentReport.title || "report", "csv");
  downloadText(filename, csvText(displayFields, displayRows()), "text/csv;charset=utf-8");
}

function renderFilterControls() {
  els.customRange.classList.toggle("hidden", state.range !== "custom");
  els.startDate.value = state.customStart;
  els.endDate.value = state.customEnd;
}

function render() {
  renderStatus();
  renderSources();
  renderSyncInfo();
  renderErrors();
  renderSidePanelState();
  renderFilterControls();
  renderKpis();
  renderLtvChart();
  renderRetentionChart();
  renderTable();
}

function renderSidePanelState() {
  document.body.classList.toggle("side-panel-collapsed", state.sidePanelCollapsed);
  els.sidePanelButton.setAttribute("aria-label", state.sidePanelCollapsed ? "显示右侧信息" : "隐藏右侧信息");
  els.sidePanelButton.setAttribute("aria-pressed", String(state.sidePanelCollapsed));
}

async function load() {
  const [status, runtime] = await Promise.all([
    fetchJson("/api/status"),
    fetchJson("/api/reports"),
  ]);
  state.status = status;
  state.runtime = runtime;
  state.sourceMode = "feishu";
  render();
}

async function refreshData() {
  els.refreshBtn.disabled = true;
  els.refreshBtn.textContent = "刷新中";
  try {
    state.runtime = await fetchJson("/api/refresh", {
      method: "POST",
      body: JSON.stringify({ sourceMode: state.sourceMode }),
    });
    state.status = state.runtime.status;
    state.sourceMode = state.runtime.sourceMode || state.sourceMode;
    render();
  } catch (error) {
    els.statusBanner.textContent = `刷新失败：${error.message}`;
    els.statusBanner.className = "status-banner error";
    els.lastRefresh.textContent = lastRefreshText(state.status);
  } finally {
    els.refreshBtn.disabled = false;
    els.refreshBtn.textContent = "刷新数据";
  }
}

async function syncFeishu() {
  if (state.sourceMode === "feishu" || state.runtime?.sourceMode === "feishu") {
    alert("飞书结果表当前数据已来自飞书结果表，无需同步。");
    return;
  }
  if (!confirm("确认将最近一次成功计算结果同步到飞书？")) return;
  els.syncBtn.disabled = true;
  els.syncBtn.textContent = "同步中";
  try {
    state.runtime = await fetchJson("/api/sync", { method: "POST", body: "{}" });
    state.status = await fetchJson("/api/status");
    render();
  } catch (error) {
    els.statusBanner.textContent = `同步失败：${error.message}`;
    els.statusBanner.className = "status-banner error";
  } finally {
    els.syncBtn.disabled = state.sourceMode === "feishu";
    els.syncBtn.textContent = "确认同步飞书";
  }
}

function bindEvents() {
  els.menuButton.addEventListener("click", () => {
    document.body.classList.toggle("nav-collapsed");
  });
  els.sidePanelButton.addEventListener("click", () => {
    state.sidePanelCollapsed = !state.sidePanelCollapsed;
    localStorage.setItem("newbieSidePanelCollapsed", String(state.sidePanelCollapsed));
    renderSidePanelState();
  });
  els.refreshBtn.addEventListener("click", refreshData);
  els.syncBtn.addEventListener("click", syncFeishu);
  els.exportBtn.addEventListener("click", exportCurrentReport);
  els.rangeButtons.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-range]");
    if (!button) return;
    state.range = button.dataset.range;
    els.rangeButtons.querySelectorAll("button").forEach((item) => item.classList.toggle("selected", item === button));
    render();
  });
    els.sourceModeButtons.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-source-mode]");
      if (!button) return;
      state.sourceMode = button.dataset.sourceMode;
    els.sourceModeButtons.querySelectorAll("button").forEach((item) => item.classList.toggle("selected", item === button));
    render();
  });
  els.compareButtons.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-dimension]");
    if (!button) return;
    state.compareDimension = button.dataset.dimension;
    els.compareButtons.querySelectorAll("button").forEach((item) => item.classList.toggle("selected", item === button));
    render();
  });
  els.ltvMetricButtons.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-metric]");
    if (!button) return;
    state.ltvMetric = button.dataset.metric;
    els.ltvMetricButtons.querySelectorAll("button").forEach((item) => item.classList.toggle("selected", item === button));
    render();
  });
  els.retentionMetricButtons.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-metric]");
    if (!button) return;
    state.retentionMetric = button.dataset.metric;
    els.retentionMetricButtons.querySelectorAll("button").forEach((item) => item.classList.toggle("selected", item === button));
    render();
  });
  els.startDate.addEventListener("change", () => {
    state.customStart = els.startDate.value;
    render();
  });
  els.endDate.addEventListener("change", () => {
    state.customEnd = els.endDate.value;
    render();
  });
}


  bindEvents();
  load().catch((error) => {
    els.statusBanner.textContent = `加载失败：${error.message}`;
    els.statusBanner.className = "status-banner error";
  });
}
