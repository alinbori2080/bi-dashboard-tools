<!-- 30 日留存看板页面：展示留存趋势、明细数据和飞书同步状态。 -->

<script setup lang="ts">
import { useRetentionDashboard } from '@/composables/useRetentionDashboard'

const dashboard = useRetentionDashboard()
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">30</span>
        <span>30 日留存数据</span>
      </div>
      <nav class="nav" aria-label="报表导航">
        <button
          class="nav-button active"
          :class="{ 'has-error': dashboard.hasBlockingErrors.value }"
          type="button"
        >
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
        <button class="icon-button" type="button" aria-label="折叠菜单" @click="dashboard.toggleNav">☰</button>
        <button
          class="icon-button"
          type="button"
          :aria-label="dashboard.sidePanelCollapsed.value ? '显示右侧信息' : '隐藏右侧信息'"
          :aria-pressed="dashboard.sidePanelCollapsed.value"
          @click="dashboard.toggleSidePanel"
        >
          ◐
        </button>
        <div class="status-line">
          <span>源目录</span>
          <strong>{{ dashboard.dataDirText.value }}</strong>
        </div>
        <div class="actions">
          <button class="primary-button" type="button" :disabled="dashboard.loading.value" @click="dashboard.refreshReports">
            {{ dashboard.loading.value ? '刷新中...' : '刷新数据' }}
          </button>
          <button class="secondary-button" type="button" :disabled="dashboard.syncButtonDisabled.value" @click="dashboard.syncFeishu">
            确认同步飞书
          </button>
          <button class="secondary-button" type="button" @click="dashboard.exportCurrentReport">导出全部</button>
        </div>
      </header>

      <section class="filter-row" aria-label="筛选">
        <div class="filter-group">
          <span class="filter-label">数据源</span>
          <div class="segmented">
            <button
              :class="{ active: dashboard.filters.dataSource === 'feishu' }"
              :disabled="dashboard.loading.value"
              type="button"
              @click="dashboard.changeSource('feishu')"
            >
              飞书结果表
            </button>
            <button
              :class="{ active: dashboard.filters.dataSource === 'local' }"
              :disabled="dashboard.loading.value"
              type="button"
              @click="dashboard.changeSource('local')"
            >
              本地结果文件
            </button>
          </div>
        </div>
        <div class="filter-group">
          <span class="filter-label">时间范围</span>
          <div class="segmented">
            <button :class="{ active: dashboard.filters.range === 'all' }" type="button" @click="dashboard.filters.range = 'all'">全部</button>
            <button :class="{ active: dashboard.filters.range === 'campaign' }" type="button" @click="dashboard.filters.range = 'campaign'">活动开启后</button>
            <button :class="{ active: dashboard.filters.range === '7' }" type="button" @click="dashboard.filters.range = '7'">近 7 天</button>
            <button :class="{ active: dashboard.filters.range === '30' }" type="button" @click="dashboard.filters.range = '30'">近 30 天</button>
            <button :class="{ active: dashboard.filters.range === 'custom' }" type="button" @click="dashboard.filters.range = 'custom'">自定义</button>
          </div>
        </div>
        <div class="date-range" :class="{ hidden: dashboard.filters.range !== 'custom' }">
          <input v-model="dashboard.filters.customStart" type="date" aria-label="开始日期" />
          <span>至</span>
          <input v-model="dashboard.filters.customEnd" type="date" aria-label="结束日期" />
        </div>
        <div class="filter-group">
          <span class="filter-label">对比维度</span>
          <div class="segmented">
            <button :class="{ active: dashboard.filters.period === '日' }" type="button" @click="dashboard.filters.period = '日'">日</button>
            <button :class="{ active: dashboard.filters.period === '周' }" type="button" @click="dashboard.filters.period = '周'">周</button>
            <button :class="{ active: dashboard.filters.period === '月' }" type="button" @click="dashboard.filters.period = '月'">月</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="filter-label">趋势指标</span>
          <div class="segmented">
            <button :class="{ active: dashboard.filters.metric === '次留' }" type="button" @click="dashboard.filters.metric = '次留'">次留</button>
            <button :class="{ active: dashboard.filters.metric === '3日留' }" type="button" @click="dashboard.filters.metric = '3日留'">3 日</button>
            <button :class="{ active: dashboard.filters.metric === '7日留' }" type="button" @click="dashboard.filters.metric = '7日留'">7 日</button>
            <button :class="{ active: dashboard.filters.metric === '14日留' }" type="button" @click="dashboard.filters.metric = '14日留'">14 日</button>
            <button :class="{ active: dashboard.filters.metric === '21日留' }" type="button" @click="dashboard.filters.metric = '21日留'">21 日</button>
            <button :class="{ active: dashboard.filters.metric === '30日留' }" type="button" @click="dashboard.filters.metric = '30日留'">30 日</button>
          </div>
        </div>
      </section>

      <section :class="dashboard.notice.value.className">{{ dashboard.notice.value.text }}</section>

      <div class="layout-grid">
        <section class="report-panel">
          <div class="section-heading">
            <div>
              <h1>{{ dashboard.reportTitle.value }}</h1>
              <p>{{ dashboard.reportDescription.value }}</p>
            </div>
            <span class="meta-text">{{ dashboard.lastRefreshText.value }}</span>
          </div>

          <p class="meta-text kpi-period">{{ dashboard.activeReport.value ? dashboard.kpiPeriod.value : '' }}</p>
          <div class="kpi-grid">
            <article v-for="item in dashboard.kpis.value" :key="item.label" class="kpi">
              <span>{{ item.label }}</span>
              <strong :class="item.tone">{{ item.value }}</strong>
              <small>{{ item.hint }}</small>
            </article>
          </div>

          <section class="chart-section">
            <div class="section-heading compact">
              <div>
                <h2>留存趋势</h2>
                <p>{{ dashboard.chartSubtitle.value }}</p>
              </div>
              <div class="legend">
                <span v-for="item in dashboard.chartLegend.value" :key="item.label">
                  <i class="swatch" :class="item.className"></i><b>{{ item.label }}</b>
                </span>
              </div>
            </div>
            <div class="chart" role="img" aria-label="30 日留存趋势" v-html="dashboard.chartHtml.value"></div>
          </section>

          <section class="table-section">
            <div class="section-heading compact">
              <h2>明细数据</h2>
              <span class="meta-text">{{ dashboard.sortedRows.value.length }} 条</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr v-if="dashboard.tableColumns.value.length">
                    <th v-for="column in dashboard.tableColumns.value" :key="column">{{ column }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, rowIndex) in dashboard.sortedRows.value" :key="rowIndex">
                    <td v-for="column in dashboard.tableColumns.value" :key="column">{{ row[column] ?? '' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </section>

        <aside class="side-panel">
          <section class="info-panel">
            <h2>源数据文件</h2>
            <div class="source-list">
              <article v-for="source in dashboard.sources.value" :key="source.path || source.name" class="source-row">
                <div class="file-badge">{{ source.name?.endsWith('.xlsx') ? 'X' : 'C' }}</div>
                <div>
                  <strong :title="source.path">{{ source.name }}</strong>
                  <span>{{ source.role }} · {{ source.updatedAt }}</span>
                </div>
              </article>
              <div v-if="!dashboard.sources.value.length" class="empty small">data 目录下没有源文件</div>
            </div>
          </section>
          <section class="info-panel">
            <h2>飞书同步</h2>
            <dl class="key-value">
              <template v-for="row in dashboard.syncRows.value" :key="row.key">
                <dt>{{ row.key }}</dt>
                <dd>
                  <a v-if="row.url" class="sync-link" :href="row.url" target="_blank" rel="noreferrer">打开</a>
                  <span v-else-if="row.disabled" class="sync-link disabled" title="未配置飞书链接">打开</span>
                  <template v-else>{{ row.value }}</template>
                </dd>
              </template>
            </dl>
          </section>
          <section class="info-panel">
            <h2>错误与提示</h2>
            <div class="message-list">
              <div v-for="message in dashboard.messages.value" :key="`${message.type}-${message.title}-${message.body}`" class="message" :class="message.type">
                <strong>{{ message.title }}</strong>
                <p>{{ message.body }}</p>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>
