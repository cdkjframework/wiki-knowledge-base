<script setup lang="ts">
/**
 * 权限管理：社区版基础角色示意 + 四张商业 edition-gate 卡。
 */
import EditionGate from '@/components/commercial/EditionGate.vue'

const roles = [
  { name: '管理员', desc: '知识库与配置全权限', scope: '本机单实例' },
  { name: '编辑', desc: '导入 / 编辑文档与分片', scope: '本机单实例' },
  { name: '只读', desc: '检索问答与只读浏览', scope: '本机单实例' },
]

const auditDemo = [
  { time: '刚刚', actor: 'local-user', action: 'query', result: '成功' },
  { time: '今天', actor: 'local-user', action: 'kb.document.add', result: '成功' },
  { time: '昨天', actor: 'system', action: 'index.rebuild', result: '成功' },
]

const gates = [
  {
    title: '多租户隔离',
    description: '按租户隔离知识库、配额与配置，满足组织级边界。',
    communityNote: '单库 / 单实例，无租户维度',
    commercialNote: '多租户数据隔离 + 配额',
  },
  {
    title: '细粒度 RBAC',
    description: '自定义角色与资源策略，细化到知识库与 API。',
    communityNote: '内置管理员 / 编辑 / 只读示意',
    commercialNote: '自定义角色 + 策略引擎',
  },
  {
    title: '操作审计',
    description: '跨主体、可导出的合规审计轨迹。',
    communityNote: '本机操作日志（示意）',
    commercialNote: '跨租户审计 + 留存策略',
  },
  {
    title: '数据加密',
    description: '静态加密与密钥托管，强化静态数据保护。',
    communityNote: '本地文件权限保护',
    commercialNote: '静态加密 + 密钥轮换',
  },
]
</script>

<template>
  <div class="perm">
    <section class="page-card">
      <h2>权限管理</h2>
      <p class="lead">社区版提供本机基础角色示意；企业隔离与合规增强见下方商业版门控，不可在本程序内解锁。</p>

      <h3>基础角色（社区版）</h3>
      <el-table :data="roles" border style="margin-top: 10px">
        <el-table-column prop="name" label="角色" width="140" />
        <el-table-column prop="desc" label="说明" />
        <el-table-column prop="scope" label="作用域" width="140" />
      </el-table>

      <h3 class="mt">资源绑定（示意）</h3>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="知识库">本机全部文档（社区版无租户切分）</el-descriptions-item>
        <el-descriptions-item label="API">/api/query · /api/kb · /api/stats</el-descriptions-item>
      </el-descriptions>

      <h3 class="mt">审计时间线（本机示意）</h3>
      <el-timeline style="margin-top: 12px; max-width: 560px">
        <el-timeline-item v-for="(item, idx) in auditDemo" :key="idx" :timestamp="item.time" placement="top">
          {{ item.actor }} · {{ item.action }} · {{ item.result }}
        </el-timeline-item>
      </el-timeline>
    </section>

    <section class="page-card gate-section">
      <div class="gate-head">
        <h2>商业版增强</h2>
        <el-tag size="small" effect="plain">edition-gate</el-tag>
      </div>
      <div class="gate-grid">
        <EditionGate
          v-for="g in gates"
          :key="g.title"
          :title="g.title"
          :description="g.description"
          :community-note="g.communityNote"
          :commercial-note="g.commercialNote"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.perm {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lead {
  margin: 8px 0 18px;
  color: var(--color-text-secondary);
  font-size: 14px;
}
h2 {
  margin: 0;
  font-size: 20px;
}
h3 {
  margin: 0;
  font-size: 15px;
}
.mt {
  margin-top: 22px;
}
.gate-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.gate-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
@media (max-width: 900px) {
  .gate-grid {
    grid-template-columns: 1fr;
  }
}
</style>
