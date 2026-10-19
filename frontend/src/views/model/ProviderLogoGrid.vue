<script setup lang="ts">
/**
 * 服务商 Logo 宫格（对齐设计稿：白底卡片 + 品牌色标）。
 */
import { computed } from 'vue'
import ProviderLogo from './ProviderLogo.vue'
import { brandsForKind, type ProviderBrand, type ProviderKind } from './providerCatalog'

const props = withDefaults(
  defineProps<{
    kind: ProviderKind
    modelValue?: string
    /** 仅展示这些 id（与 API 交集）；空则展示品牌表） */
    availableIds?: string[]
  }>(),
  {
    modelValue: '',
    availableIds: undefined,
  },
)

const emit = defineEmits<{
  'update:modelValue': [string]
  select: [ProviderBrand]
}>()

const tiles = computed(() => {
  let list = brandsForKind(props.kind)
  if (props.availableIds?.length) {
    const allow = new Set(props.availableIds.map((x) => x.toLowerCase()))
    // available 里有 dashscope 时仍展示通义千问（qwen）
    list = list.filter((b) => {
      if (allow.has(b.id)) return true
      if (b.id === 'qwen' && (allow.has('dashscope') || allow.has('qwen'))) return true
      if (b.id === 'kimi' && (allow.has('moonshot') || allow.has('kimi'))) return true
      return false
    })
  }
  return list
})

const groups = computed(() => {
  const order: Array<{ key: ProviderBrand['group']; title: string }> = [
    { key: 'local', title: '本地加载' },
    { key: 'china', title: '国内模型' },
    { key: 'global', title: '国际模型' },
  ]
  return order
    .map((g) => ({
      ...g,
      items: tiles.value.filter((t) => t.group === g.key),
    }))
    .filter((g) => g.items.length > 0)
})

function onPick(b: ProviderBrand) {
  emit('update:modelValue', b.id)
  emit('select', b)
}
</script>

<template>
  <div class="prov-grid">
    <div v-for="g in groups" :key="g.key" class="prov-grid__group">
      <div class="prov-grid__group-title">{{ g.title }}</div>
      <div class="prov-grid__tiles">
        <button
          v-for="b in g.items"
          :key="b.id"
          type="button"
          class="prov-grid__tile"
          :class="{ 'is-active': modelValue === b.id }"
          @click="onPick(b)"
        >
          <ProviderLogo :provider-id="b.id" :brand="b" :selected="modelValue === b.id" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prov-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.prov-grid__group-title {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 8px;
  letter-spacing: 0.02em;
}

.prov-grid__tiles {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

@media (max-width: 900px) {
  .prov-grid__tiles {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .prov-grid__tiles {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.prov-grid__tile {
  appearance: none;
  border: 1px solid #e8eef7;
  background: #fff;
  border-radius: 12px;
  padding: 12px 8px 10px;
  cursor: pointer;
  /* 固定边框占位，避免选中/悬停撑布局 */
  box-shadow: inset 0 0 0 0 transparent;
  transition: border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
}

.prov-grid__tile:hover {
  border-color: #b9cdff;
  background: #fafcff;
}

.prov-grid__tile.is-active {
  border-color: #2f6bff;
  background: #f5f8ff;
  box-shadow: inset 0 0 0 1px #2f6bff;
}

.prov-grid__tile:focus-visible {
  outline: none;
  border-color: #2f6bff;
}
</style>
