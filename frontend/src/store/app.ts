import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

/**
 * 应用壳层状态：侧栏折叠、版本标识等。
 */
export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const edition = ref<'community' | 'commercial'>(
    (import.meta.env.VITE_EDITION as 'community' | 'commercial') || 'community',
  )
  const title = ref(import.meta.env.VITE_APP_TITLE || 'WIKI 本地知识库')

  const isCommercial = computed(() => edition.value === 'commercial')

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    sidebarCollapsed,
    edition,
    title,
    isCommercial,
    toggleSidebar,
  }
})
