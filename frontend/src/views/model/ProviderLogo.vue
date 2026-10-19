<script setup lang="ts">
/**
 * 服务商 Logo：彩色圆角底 + SVG 品牌图标。
 */
import { computed } from 'vue'
import { getProviderBrand, type ProviderBrand } from './providerCatalog'
import ProviderIcon from './ProviderIcon.vue'

const props = withDefaults(
  defineProps<{
    providerId: string
    brand?: ProviderBrand
    selected?: boolean
    size?: 'sm' | 'md'
    showLabel?: boolean
  }>(),
  {
    selected: false,
    size: 'md',
    showLabel: true,
  },
)

const brand = computed(() => props.brand || getProviderBrand(props.providerId))
</script>

<template>
  <div
    class="prov-logo"
    :class="[`prov-logo--${size}`, { 'is-selected': selected }]"
    :title="brand.label"
  >
    <span
      class="prov-logo__mark"
      :style="{ background: brand.color, color: brand.markColor || '#fff' }"
    >
      <ProviderIcon :provider-id="brand.id" />
    </span>
    <span v-if="showLabel" class="prov-logo__label">{{ brand.label }}</span>
  </div>
</template>

<style scoped>
.prov-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  user-select: none;
}

.prov-logo__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
  /* 预留环宽，选中时不撑开 */
  outline: 2px solid transparent;
  outline-offset: 2px;
}

.prov-logo--md .prov-logo__mark {
  width: 48px;
  height: 48px;
}

.prov-logo--sm .prov-logo__mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  outline-width: 1px;
  outline-offset: 1px;
}

.prov-logo__label {
  font-size: 12px;
  line-height: 1.2;
  font-weight: 600;
  color: #334155;
  text-align: center;
  max-width: 72px;
  min-height: 1.2em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.prov-logo--sm .prov-logo__label {
  font-size: 11px;
  max-width: 56px;
}

.prov-logo.is-selected .prov-logo__mark {
  outline-color: #2f6bff;
}

.prov-logo.is-selected .prov-logo__label {
  color: #2f6bff;
}
</style>
