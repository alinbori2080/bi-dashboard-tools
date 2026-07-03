<!-- 30 日留存看板页面：展示留存趋势、明细数据和飞书同步状态。 -->

<script setup lang="ts">
import { onMounted } from 'vue'

import { mountRetentionDashboard } from '@/composables/useRetentionDashboard'

onMounted(() => {
  void mountRetentionDashboard()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">30</span>
        <span>30 日留存数据</span>
      </div>
      <nav class="nav" aria-label="报表导航">
        <button class="nav-button active" data-report="daily" type="button">
          <span aria-hidden="true">↗</span>
          后续留存数据
        </button>
      </nav>
      <div class="local-mode">
        <span class="dot"></span>
        本地服务
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <button id="menuButton" class="icon-button" type="button" aria-label="折叠菜单">☰</button>
        <button id="sidePanelButton" class="icon-button" type="button" aria-label="隐藏右侧信息">◐</button>
        <div class="status-line">
          <span>源目录</span>
          <strong id="dataDir">读取中</strong>
        </div>
        <div class="actions">
          <button id="refreshButton" class="primary-button" type="button">刷新数据</button>
          <button id="syncButton" class="secondary-button" type="button">确认同步飞书</button>
          <button id="exportButton" class="secondary-button" type="button">导出全部</button>
        </div>
      </header>

      <section class="filter-row" aria-label="筛选">
        <div class="filter-group">
          <span class="filter-label">数据源</span>
          <div id="sourceModeTabs" class="segmented">
            <button class="active" data-source-mode="feishu" type="button">飞书结果表</button>
            <button data-source-mode="local" type="button">本地结果文件</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="filter-label">时间范围</span>
          <div id="rangeTabs" class="segmented">
            <button class="active" data-range="all" type="button">全部</button>
            <button data-range="campaign" type="button">活动开启后</button>
            <button data-range="7" type="button">近 7 天</button>
            <button data-range="30" type="button">近 30 天</button>
            <button data-range="custom" type="button">自定义</button>
          </div>
        </div>
        <div id="customRange" class="date-range hidden">
          <input id="startDateInput" type="date" aria-label="开始日期" />
          <span>至</span>
          <input id="endDateInput" type="date" aria-label="结束日期" />
        </div>
        <div id="periodFilter" class="filter-group">
          <span class="filter-label">对比维度</span>
          <div id="periodTabs" class="segmented">
            <button class="active" data-period="日" type="button">日</button>
            <button data-period="周" type="button">周</button>
            <button data-period="月" type="button">月</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="filter-label">趋势指标</span>
          <div id="metricTabs" class="segmented">
            <button class="active" data-metric="次留" type="button">次留</button>
            <button data-metric="3日留" type="button">3 日</button>
            <button data-metric="7日留" type="button">7 日</button>
            <button data-metric="14日留" type="button">14 日</button>
            <button data-metric="21日留" type="button">21 日</button>
            <button data-metric="30日留" type="button">30 日</button>
          </div>
        </div>
      </section>

      <section id="noticeBand" class="status-banner muted">正在读取本地状态</section>

      <div class="layout-grid">
        <section class="report-panel">
          <div class="section-heading">
            <div>
              <h1 id="reportTitle">每日结果</h1>
              <p id="reportDescription">按注册日期展示 2-30 日留存。</p>
            </div>
            <span id="lastRefresh" class="meta-text"></span>
          </div>

          <p id="kpiPeriod" class="meta-text kpi-period"></p>
          <div id="kpiGrid" class="kpi-grid"></div>

          <section class="chart-section">
            <div class="section-heading compact">
              <div>
                <h2 id="chartTitle">留存趋势</h2>
                <p id="chartSubtitle"></p>
              </div>
              <div id="chartLegend" class="legend"></div>
            </div>
            <div id="chart" class="chart" role="img" aria-label="30 日留存趋势"></div>
          </section>

          <section class="table-section">
            <div class="section-heading compact">
              <h2>明细数据</h2>
              <span id="rowCount" class="meta-text">0 条</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead id="tableHead"></thead>
                <tbody id="tableBody"></tbody>
              </table>
            </div>
          </section>
        </section>

        <aside class="side-panel">
          <section class="info-panel">
            <h2>源数据文件</h2>
            <div id="sourceList" class="source-list"></div>
          </section>
          <section class="info-panel">
            <h2>飞书同步</h2>
            <dl id="syncInfo" class="key-value"></dl>
          </section>
          <section class="info-panel">
            <h2>错误与提示</h2>
            <div id="messageList" class="message-list"></div>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>
