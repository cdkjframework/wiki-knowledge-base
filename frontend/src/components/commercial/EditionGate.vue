<script setup lang="ts">
/**
 * 商业版能力门控卡片：社区版灰底+锁标，不可在本程序内「解锁」。
 */
defineProps<{
  title: string
  description: string
  communityNote?: string
  commercialNote?: string
}>()
</script>

<template>
  <div class="edition-gate">
    <div class="edition-gate__top">
      <el-icon class="edition-gate__lock"><Lock /></el-icon>
      <span class="edition-gate__title">{{ title }}</span>
      <el-tag size="small" class="edition-gate__badge" effect="plain">商业版专属</el-tag>
    </div>
    <p class="edition-gate__desc">{{ description }}</p>
    <div class="edition-gate__cmp">
      <div v-if="communityNote" class="row">
        <b>社区版</b>：{{ communityNote }}
      </div>
      <div v-if="commercialNote" class="row">
        <b>商业版</b>：{{ commercialNote }}
      </div>
    </div>
    <p class="edition-gate__hint">社区版与商业版为独立安装产物，无法在本程序内切换或解锁。</p>
  </div>
</template>

<style scoped>
.edition-gate {
  background: #f1f3f6;
  border: 1px dashed var(--color-border-strong);
  border-radius: 12px;
  padding: 18px 20px;
}
.edition-gate__top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.edition-gate__lock {
  color: #8792a2;
  font-size: 18px;
}
.edition-gate__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.edition-gate__badge {
  margin-left: auto;
  color: #5a6675 !important;
  border-color: var(--color-border-strong) !important;
  background: #e8ebef !important;
}
.edition-gate__desc {
  margin: 0 0 12px;
  font-size: 13px;
  color: #5a6675;
  line-height: 1.55;
}
.edition-gate__cmp {
  font-size: 12.5px;
  border-top: 1px solid var(--color-border-strong);
  padding-top: 12px;
  color: #5a6675;
}
.edition-gate__cmp .row {
  padding: 3px 0;
}
.edition-gate__hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
</style>
