<script setup lang="ts">
/**
 * 指标看板：拉取真实 /stats，KPI 用验收线占位（不编造业务评测结果）。
 */
import { onMounted, ref } from 'vue'
import { getStats, type KbStats } from '@/api/stats'

const loading = ref(false)
const stats = ref<KbStats | null>(null)
const error = ref('')

/** 产品验收线占位（非运行时实测） */
const acceptanceKpis = [
  { key: 'Recall@5', target: '≥ 0.85', note: '评测集验收线（占位）' },
  { key: 'NDCG@10', target: '≥ 0.70', note: '评测集验收线（占位）' },
  { key: '检索 p95', target: '≤ 目标线', note: '待评测流水线接入' },
  { key: 'TTFT p95', target: '≤ 目标线', note: '流式首 token 延迟（占位）' },
]

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const data = await getStats()
    stats.value = data.stats || {}
  } catch (err) {
    error.value = (err as Error).message || '无法读取统计'
    stats.value = null
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="metrics">
    <section class="page-card">
      <div class="metrics__head">
        <h2>指标看板</h2>
        <el-button :loading="loading" @click="refresh">刷新统计</el-button>
      </div>
      <p class="muted">顶部 KPI 为 PRD 验收线占位；下方为当前知识库运行态统计（/api/stats）。</p>

      <div class="kpi-grid">
        <div v-for="item in acceptanceKpis" :key="item.key" class="kpi-card">
          <div class="kpi-card__label">{{ item.key }}</div>
          <div class="kpi-card__value">{{ item.target }}</div>
          <div class="kpi-card__note">{{ item.note }}</div>
        </div>
      </div>
    </section>

    <section class="page-card" style="margin-top: 16px">
      <h3>运行态统计</h3>
      <el-alert v-if="error" type="warning" :title="error" :closable="false" style="margin: 12px 0" />
      <el-descriptions v-if="stats" :column="2" border>
        <el-descriptions-item
          v-for="(val, key) in stats"
          :key="String(key)"
          :label="String(key)"
        >
          {{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}
        </el-descriptions-item>
      </el-descriptions>
      <p v-else-if="!loading && !error" class="muted">暂无统计数据</p>

      <div class="trend-placeholder">
        <h4>趋势图</h4>
        <p class="muted">延迟 / 吞吐 / 命中率趋势将在评测流水线接入后以图表展示（当前占位）。</p>
        <div class="trend-box">SVG / ECharts 预留</div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.metrics__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.metrics h2,
.metrics h3,
.metrics h4 {
  margin: 0;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin: 8px 0 16px;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.kpi-card {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 14px;
  background: var(--color-bg-subtle);
}
.kpi-card__label {
  font-size: 12px;
  color: var(--color-text-secondary);
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
.trend-placeholder {
  margin-top: 20px;
}
.trend-box {
  height: 160px;
  border: 1px dashed var(--color-border-strong);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  background: var(--color-bg-subtle);
}
@media (max-width: 960px) {
  .kpi-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
