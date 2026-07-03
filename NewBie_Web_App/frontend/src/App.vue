<!-- 新锐攻略用户数据页面：展示推送用户留存付费数据。 -->

<script setup lang="ts">
import { onMounted } from 'vue'

import { mountNewbieDashboard } from '@/composables/useNewbieDashboard'

onMounted(() => {
  void mountNewbieDashboard()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">N</span>
        <span>新锐攻略用户数据</span>
      </div>
      <nav class="nav" aria-label="报表导航">
        <button class="nav-button active" type="button">
          <span aria-hidden="true">↗</span>
          推送用户留存付费
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
        <button id="sidePanelButton" class="icon-button" type="button" aria-label="隐藏右侧信息">◨</button>
        <div class="status-line">
          <span>源目录</span>
          <strong id="pathLine">读取中</strong>
        </div>
        <div class="actions">
          <button id="refreshBtn" class="primary-button" type="button">刷新数据</button>
          <button id="syncBtn" class="secondary-button" type="button">确认同步飞书</button>
          <button id="exportBtn" class="secondary-button" type="button">导出 CSV</button>
        </div>
      </header>

      <section class="filter-row" aria-label="筛选">
        <div class="filter-group">
          <span class="filter-label">数据源</span>
          <div id="sourceModeButtons" class="segmented">
            <button data-source-mode="feishu" class="selected" type="button">飞书结果表</button>
            <button data-source-mode="local" type="button">本地文件</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="filter-label">时间范围</span>
          <div id="rangeButtons" class="segmented">
            <button data-range="all" class="selected" type="button">全部</button>
            <button data-range="7" type="button">近7天</button>
            <button data-range="30" type="button">近30天</button>
            <button data-range="custom" type="button">自定义</button>
          </div>
        </div>
        <div id="customRange" class="date-range hidden">
          <input id="startDate" type="date" aria-label="开始日期" />
          <span>至</span>
          <input id="endDate" type="date" aria-label="结束日期" />
        </div>
        <div class="filter-group">
          <span class="filter-label">对比维度</span>
          <div id="compareButtons" class="segmented">
            <button data-dimension="日" class="selected" type="button">日</button>
            <button data-dimension="周" type="button">周</button>
            <button data-dimension="月" type="button">月</button>
          </div>
        </div>
      </section>

      <section id="statusBanner" class="status-banner muted">正在读取本地状态</section>

      <div class="layout-grid">
        <section class="report-panel">
          <section id="errorPanel" class="error-panel hidden"></section>

          <div class="section-heading">
            <div>
              <h1>推送用户留存付费</h1>
              <p>按推送批次对比实验组、对照组、大盘留存与 LTV 差值</p>
            </div>
            <span id="lastRefresh" class="meta-text">最后刷新：未刷新</span>
          </div>

          <p id="kpiPeriod" class="meta-text kpi-period"></p>
          <section id="kpiGrid" class="kpi-grid"></section>

          <section class="chart-section">
            <div class="section-heading compact">
              <div>
                <h2>LTV 趋势</h2>
                <p id="ltvSubtitle">按当前筛选范围展示</p>
              </div>
              <div id="ltvMetricButtons" class="segmented metric-tabs">
                <button data-metric="LTV7" class="selected" type="button">LTV7</button>
                <button data-metric="LTV15" type="button">LTV15</button>
                <button data-metric="LTV30" type="button">LTV30</button>
              </div>
              <div class="legend">
                <span><i class="swatch blue"></i><b>实验组</b></span>
                <span><i class="swatch teal"></i><b>对照组</b></span>
                <span><i class="swatch orange"></i><b>差值</b></span>
              </div>
            </div>
            <div id="ltvChart" class="chart" role="img" aria-label="LTV 趋势"></div>
          </section>

          <section class="chart-section">
            <div class="section-heading compact">
              <div>
                <h2>留存率趋势</h2>
                <p id="retentionSubtitle">实验组、对照组与大盘对比</p>
              </div>
              <div id="retentionMetricButtons" class="segmented metric-tabs">
                <button data-metric="次日留存率" class="selected" type="button">次日</button>
                <button data-metric="3日留存率" type="button">3日</button>
                <button data-metric="7日留存率" type="button">7日</button>
              </div>
              <div class="legend">
                <span><i class="swatch blue"></i><b>实验组</b></span>
                <span><i class="swatch teal"></i><b>对照组</b></span>
                <span><i class="swatch gray"></i><b>大盘</b></span>
              </div>
            </div>
            <div id="retentionChart" class="chart" role="img" aria-label="留存率趋势"></div>
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
        </aside>
      </div>
    </main>
  </div>
</template>
