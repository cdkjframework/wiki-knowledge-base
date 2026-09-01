<script setup lang="ts">
/**
 * 产品概览：Hero、六项能力、用户分群、社商对比（无门户、无版本切换器）。
 */
import { useRouter } from 'vue-router'

const router = useRouter()

const features = [
  { title: '混合检索', desc: 'BM25 与向量并行召回，经 Rerank 融合，兼顾字面与语义。', tag: 'BM25 ∪ 向量' },
  { title: '语义递归分片', desc: '按标题与语义边界切分，避免硬截断导致的上下文破碎。', tag: '语义边界' },
  { title: '多模型中立', desc: 'Embedding / Rerank / 生成模型可插拔，不绑定单一厂商。', tag: '可插拔' },
  { title: '本地隐私', desc: '索引与语料留存内网，可选本地推理，数据不出边界。', tag: '数据不出内网' },
  { title: '开放接口与 MCP', desc: 'REST API 与 MCP 接入，便于嵌入工作流与智能体。', tag: 'REST + MCP' },
  { title: '评测可观测', desc: '指标看板与验收线可视化，改动可量化回归。', tag: '可观测' },
]

const segments = [
  { title: '个人知识工作者', desc: '把笔记与资料变成可对话的知识库。', points: ['本地隐私，零云依赖', '开箱即用'] },
  { title: '开发者', desc: '通过 API / MCP 嵌入应用。', points: ['开放 REST API', '多模型可插拔'] },
  { title: '中小企业', desc: '成本可控的自托管知识中枢。', points: ['社区版永久免费', '一套部署服务团队'] },
  { title: '企业机构', desc: '满足合规与隔离要求。', points: ['多租户隔离（商业版）', '审计与 RBAC（商业版）'] },
]

type Cell = 'yes' | 'no' | 'partial'

interface CompareRow {
  id: string
  name: string
  community: Cell
  commercial: Cell
  group?: string
}

const compareRows: CompareRow[] = [
  { group: '质量主轴', id: 'KB-01', name: '混合检索（BM25 ∪ 向量 + Rerank）', community: 'yes', commercial: 'yes' },
  { id: 'KB-02', name: '语义递归分片', community: 'no', commercial: 'yes' },
  { id: 'KB-10', name: '评测集', community: 'yes', commercial: 'yes' },
  { id: 'KB-11', name: '指标看板', community: 'yes', commercial: 'yes' },
  { id: 'KB-12', name: '引用归因与流式输出', community: 'yes', commercial: 'yes' },
  { id: 'KB-17', name: '多轮查询改写', community: 'yes', commercial: 'yes' },
  { group: '企业安全与治理', id: 'KB-03', name: '多租户隔离', community: 'no', commercial: 'yes' },
  { id: 'KB-04', name: '细粒度角色权限', community: 'partial', commercial: 'yes' },
  { id: 'KB-05', name: '操作审计', community: 'partial', commercial: 'yes' },
  { id: 'KB-06', name: '数据加密', community: 'no', commercial: 'yes' },
  { group: '集成与增强', id: 'KB-07', name: 'MCP 调度增强', community: 'partial', commercial: 'yes' },
  { id: 'KB-09', name: '连接器 / OCR 增强', community: 'no', commercial: 'yes' },
  { id: 'KB-14', name: '版本化与回滚', community: 'no', commercial: 'yes' },
  { id: 'KB-15', name: '增量索引', community: 'partial', commercial: 'yes' },
]

function cellLabel(v: Cell) {
  if (v === 'yes') return '支持'
  if (v === 'partial') return '基础'
  return '—'
}

function goQa() {
  router.push('/retrieval-qa')
}

function scrollEditions() {
  document.getElementById('editions')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <div class="overview">
    <section class="hero page-card">
      <el-tag effect="plain" type="success" size="small">社区版概览</el-tag>
      <h1>本地优先的开源知识库，检索更准、答案可溯源、数据不出内网</h1>
      <p>
        混合检索、语义分片、引用归因与评测可观测，一套可自托管的 RAG 系统。从个人笔记到企业知识中枢，按需扩展。
      </p>
      <div class="hero-actions">
        <el-button type="primary" @click="goQa">开始检索问答</el-button>
        <el-button @click="scrollEditions">对比社区版与商业版</el-button>
      </div>
      <div class="hero-shot" aria-hidden="true">
        <div class="hero-shot__bar"><span /><span /><span /></div>
        <div class="hero-shot__body">
          <div class="hs-col" /><div class="hs-col main" /><div class="hs-col" />
        </div>
      </div>
    </section>

    <section class="page-card section">
      <h2>六项核心能力</h2>
      <p class="lead">围绕「检索准、答案可信、数据可控」构建。</p>
      <div class="feature-grid">
        <article v-for="f in features" :key="f.title" class="feature">
          <h3>{{ f.title }}</h3>
          <p>{{ f.desc }}</p>
          <el-tag size="small" effect="plain">{{ f.tag }}</el-tag>
        </article>
      </div>
    </section>

    <section class="page-card section">
      <h2>谁在使用</h2>
      <p class="lead">社区版覆盖个人与开发者；企业合规由商业版独立产物增强。</p>
      <div class="segment-grid">
        <article v-for="s in segments" :key="s.title" class="segment">
          <h3>{{ s.title }}</h3>
          <p>{{ s.desc }}</p>
          <ul>
            <li v-for="p in s.points" :key="p">{{ p }}</li>
          </ul>
        </article>
      </div>
    </section>

    <section id="editions" class="page-card section">
      <h2>社区版与商业版对比</h2>
      <p class="lead">
        两版为<strong>独立安装 / 独立部署</strong>，不在同一程序内切换。下表为能力边界摘要（完整清单见产品 PRD）。
      </p>
      <el-table :data="compareRows" border stripe class="compare-table">
        <el-table-column label="能力" min-width="280">
          <template #default="{ row }">
            <div v-if="row.group" class="group-label">{{ row.group }}</div>
            <div>
              <el-tag size="small" effect="plain" class="kb-tag">{{ row.id }}</el-tag>
              {{ row.name }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="社区版" width="120" align="center">
          <template #default="{ row }">
            <span :class="['cell', row.community]">{{ cellLabel(row.community) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="商业版" width="120" align="center">
          <template #default="{ row }">
            <span :class="['cell', row.commercial]">{{ cellLabel(row.commercial) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="cta">
        <el-button type="primary" @click="goQa">进入检索问答</el-button>
        <el-button @click="router.push('/permissions')">查看权限页门控示意</el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.hero {
  text-align: center;
  padding: 36px 28px 28px;
}
.hero h1 {
  margin: 14px auto 12px;
  max-width: 820px;
  font-size: 28px;
  line-height: 1.25;
  letter-spacing: -0.02em;
}
.hero > p {
  margin: 0 auto 20px;
  max-width: 680px;
  color: var(--color-text-secondary);
  font-size: 15px;
  line-height: 1.6;
}
.hero-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-bottom: 28px;
}
.hero-shot {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--color-bg-subtle);
  text-align: left;
}
.hero-shot__bar {
  display: flex;
  gap: 6px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  background: #fff;
}
.hero-shot__bar span {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-border-strong);
}
.hero-shot__body {
  display: grid;
  grid-template-columns: 1fr 1.4fr 1fr;
  gap: 12px;
  padding: 16px;
  min-height: 160px;
}
.hs-col {
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: #fff;
  min-height: 120px;
}
.hs-col.main {
  background: linear-gradient(180deg, #fff 0%, var(--color-primary-subtle) 100%);
}
.section h2 {
  margin: 0 0 6px;
  font-size: 20px;
}
.lead {
  margin: 0 0 18px;
  color: var(--color-text-secondary);
  font-size: 14px;
}
.feature-grid,
.segment-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.segment-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.feature,
.segment {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
  background: var(--color-bg-subtle);
}
.feature h3,
.segment h3 {
  margin: 0 0 8px;
  font-size: 15px;
}
.feature p,
.segment p {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.55;
}
.segment ul {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-secondary);
  font-size: 13px;
}
.group-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
}
.kb-tag {
  margin-right: 6px;
}
.cell.yes {
  color: var(--color-success);
  font-weight: 600;
}
.cell.partial {
  color: var(--color-link);
}
.cell.no {
  color: var(--color-text-tertiary);
}
.cta {
  margin-top: 18px;
  display: flex;
  gap: 10px;
}
@media (max-width: 1100px) {
  .feature-grid,
  .segment-grid,
  .hero-shot__body {
    grid-template-columns: 1fr;
  }
  .hero h1 {
    font-size: 22px;
  }
}
</style>
