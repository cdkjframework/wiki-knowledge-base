<script setup lang="ts">
/**
 * 指标看板（KB-11）：KPI 来自最近一次 KB-10 评测报告，不再是占位假数。
 *
 * 没跑过评测就照实显示空态并给出命令，绝不用验收线冒充实测值。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getStats, type KbStats } from '@/api/stats'
import {
  getMetricsDashboard,
  type EvalReportSummary,
  type MetricKpi,
  type MetricsDashboard,
} from '@/api/metrics'

const loading = ref(false)
const stats = ref<KbStats | null>(null)
const statsError = ref('')
const dashboard = ref<MetricsDashboard | null>(null)
const metricsError = ref('')

const kpis = computed<MetricKpi[]>(() => dashboard.value?.kpis || [])
const latest = computed<EvalReportSummary | null>(() => dashboard.value?.latest || null)
const history = computed<EvalReportSummary[]>(() => dashboard.value?.history || [])
const hasReport = computed(() => Boolean(dashboard.value?.available))

const STATUS_TEXT: Record<string, string> = {
  pass: '达标',
  fail: '未达标',
  unknown: '无数据',
}

/** /api/stats 的字段名对照；LM Studio、GPU 是专有名词，保留原样 */
const STAT_LABELS: Record<string, string> = {
  persist_dir: '持久化目录',
  model_cache_dir: '模型缓存目录',
  document_count: '文档数',
  chunk_count: '分片数',
  dimension: '向量维度',
  index_total: '索引向量总数',
  embedding_model: '嵌入模型',
  reranker_model: '重排序模型',
  chat_model: '对话模型',
  use_lm_studio_chat: '使用 LM Studio 对话',
  loaded_models: '已加载模型',
  models_memory_total: '模型内存合计',
  process_memory: '进程内存',
  gpu_memory: '显存占用',
  system_usage: '系统资源占用',
  gpu_usage: 'GPU 占用',
  processes: '相关进程',
}

/** 后端新加字段时不至于漏显示，兜底回退到原始键名 */
function statLabel(key: string) {
  return STAT_LABELS[key] || key
}

function statValue(value: unknown) {
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

/** 历史按时间正序画趋势；接口给的是最新在前 */
const trendPoints = computed(() => {
  const values = history.value
    .map((row) => row['recall@5'])
    .filter((v): v is number => typeof v === 'number')
    .reverse()
  if (values.length < 2) return ''
  const width = 100
  const height = 28
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const span = max - min || 1
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width
      const y = height - ((value - min) / span) * height
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
})

function formatNumber(value: number | null | undefined, digits = 3) {
  return typeof value === 'number' ? value.toFixed(digits) : '—'
}

function formatTime(value: string) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

async function refresh() {
  loading.value = true
  metricsError.value = ''
  statsError.value = ''
  const [metricsResult, statsResult] = await Promise.allSettled([
    getMetricsDashboard(),
    getStats(),
  ])

  if (metricsResult.status === 'fulfilled') {
    dashboard.value = metricsResult.value
  } else {
    metricsError.value = (metricsResult.reason as Error)?.message || '无法读取评测指标'
    dashboard.value = null
  }

  if (statsResult.status === 'fulfilled') {
    stats.value = statsResult.value.stats || {}
  } else {
    statsError.value = (statsResult.reason as Error)?.message || '无法读取统计'
    stats.value = null
  }
  loading.value = false
}

/** 导出历史记录；在前端拼是为了不给后端加一条二进制响应通路 */
function exportCsv() {
  if (!history.value.length) {
    ElMessage.warning('暂无评测记录可导出')
    return
  }
  const headers = [
    '生成时间',
    '题集',
    '题目数',
    '失败题数',
    'Recall@3',
    'Recall@5',
    'NDCG@10',
    'MRR',
    '检索p95(ms)',
    '总耗时(s)',
  ]
  const rows = history.value.map((row) => [
    row.generated_at,
    row.dataset_path,
    row.case_count,
    row.failed_count,
    formatNumber(row['recall@3']),
    formatNumber(row['recall@5']),
    formatNumber(row['ndcg@10']),
    formatNumber(row.mrr),
    formatNumber(row.latency_p95_ms, 1),
    formatNumber(row.total_seconds, 2),
  ])
  const escape = (cell: unknown) => `"${String(cell ?? '').replace(/"/g, '""')}"`
  const csv = [headers, ...rows].map((line) => line.map(escape).join(',')).join('\r\n')
  // 带 BOM，免得 Excel 打开中文表头是乱码
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `kb-eval-metrics-${Date.now()}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}

onMounted(refresh)
</script>

<template>
  <div class="metrics">
    <section class="page-card">
      <div class="metrics__head">
        <h2>指标看板</h2>
        <div class="metrics__actions">
          <el-button :disabled="!history.length" @click="exportCsv">导出 CSV</el-button>
          <el-button type="primary" :loading="loading" @click="refresh">刷新</el-button>
        </div>
      </div>
      <p class="muted">
        KPI 取自最近一次评测报告（KB-10），与跑分结果同源；验收线可在 <code>conf/config.json</code>
        的 <code>metrics.targets</code> 覆盖。
      </p>

      <el-alert
        v-if="metricsError"
        type="warning"
        :title="metricsError"
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-alert
        v-else-if="!hasReport && !loading"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
        :title="dashboard?.hint || '尚未跑过评测'"
      />

      <div class="kpi-grid">
        <div v-for="item in kpis" :key="item.key" class="kpi-card" :class="`is-${item.status}`">
          <div class="kpi-card__label">
            {{ item.label }}
            <span class="kpi-card__badge" :class="`is-${item.status}`">
              {{ STATUS_TEXT[item.status] }}
            </span>
          </div>
          <div class="kpi-card__value">{{ item.display }}</div>
          <div class="kpi-card__note">验收线 {{ item.target_display }}</div>
        </div>
      </div>
    </section>

    <section v-if="hasReport" class="page-card" style="margin-top: 16px">
      <h3>最近一次评测</h3>
      <el-descriptions :column="3" border style="margin-top: 12px">
        <el-descriptions-item label="生成时间">{{ formatTime(latest?.generated_at || '') }}</el-descriptions-item>
        <el-descriptions-item label="题集">{{ latest?.dataset_path || '—' }}</el-descriptions-item>
        <el-descriptions-item label="题目数">{{ latest?.case_count ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="MRR">{{ formatNumber(latest?.mrr) }}</el-descriptions-item>
        <el-descriptions-item label="检索深度 top_k">{{ latest?.top_k ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="总耗时">{{ formatNumber(latest?.total_seconds, 2) }} s</el-descriptions-item>
      </el-descriptions>
      <p v-if="latest?.failed_count" class="warn-text">
        有 {{ latest.failed_count }} 道题检索报错，详见报告 error 字段。
      </p>
    </section>

    <section class="page-card" style="margin-top: 16px">
      <div class="metrics__head">
        <h3>评测记录</h3>
        <svg v-if="trendPoints" class="trend" viewBox="0 0 100 28" preserveAspectRatio="none">
          <polyline :points="trendPoints" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
      </div>
      <p class="muted">折线为 Recall@5 随时间的变化（左旧右新）。</p>

      <el-table v-if="history.length" :data="history" size="small" border>
        <el-table-column label="生成时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.generated_at) }}</template>
        </el-table-column>
        <el-table-column label="题目数" prop="case_count" width="90" />
        <el-table-column label="Recall@3" width="100">
          <template #default="{ row }">{{ formatNumber(row['recall@3']) }}</template>
        </el-table-column>
        <el-table-column label="Recall@5" width="100">
          <template #default="{ row }">{{ formatNumber(row['recall@5']) }}</template>
        </el-table-column>
        <el-table-column label="NDCG@10" width="100">
          <template #default="{ row }">{{ formatNumber(row['ndcg@10']) }}</template>
        </el-table-column>
        <el-table-column label="MRR" width="90">
          <template #default="{ row }">{{ formatNumber(row.mrr) }}</template>
        </el-table-column>
        <el-table-column label="检索 p95" width="110">
          <template #default="{ row }">{{ formatNumber(row.latency_p95_ms, 1) }} ms</template>
        </el-table-column>
      </el-table>
      <p v-else class="muted">暂无评测记录。</p>
    </section>

    <section class="page-card" style="margin-top: 16px">
      <h3>运行态统计</h3>
      <el-alert v-if="statsError" type="warning" :title="statsError" :closable="false" style="margin: 12px 0" />
      <el-descriptions v-if="stats" :column="2" border>
        <el-descriptions-item
          v-for="(val, key) in stats"
          :key="String(key)"
          :label="statLabel(String(key))"
        >
          <pre v-if="val && typeof val === 'object'" class="stat-json">{{ statValue(val) }}</pre>
          <span v-else>{{ statValue(val) }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <p v-else-if="!loading && !statsError" class="muted">暂无统计数据</p>
    </section>
  </div>
</template>

<style scoped>
.metrics__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.metrics__actions {
  display: flex;
  gap: 8px;
}
.metrics h2,
.metrics h3 {
  margin: 0;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin: 8px 0 16px;
}
.warn-text {
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--el-color-warning);
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.kpi-card {
  border: 1px solid var(--color-border);
  border-left-width: 3px;
  border-radius: 12px;
  padding: 14px;
  background: var(--color-bg-subtle);
}
.kpi-card.is-pass {
  border-left-color: var(--el-color-success);
}
.kpi-card.is-fail {
  border-left-color: var(--el-color-danger);
}
.kpi-card.is-unknown {
  border-left-color: var(--color-border-strong);
}
.kpi-card__label {
  font-size: 12px;
  color: var(--color-text-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.kpi-card__badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
}
.kpi-card__badge.is-pass {
  color: var(--el-color-success);
  border-color: var(--el-color-success-light-5);
}
.kpi-card__badge.is-fail {
  color: var(--el-color-danger);
  border-color: var(--el-color-danger-light-5);
}
.kpi-card__value {
  margin-top: 6px;
  font-size: 22px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.kpi-card__note {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
/* 模型 / 进程这类嵌套对象一行铺开根本没法看，折行显示并限高 */
.stat-json {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text-secondary);
}
.trend {
  width: 160px;
  height: 28px;
  color: var(--el-color-primary);
}
@media (max-width: 960px) {
  .kpi-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
