<script setup lang="ts">
/**
 * 应用主布局：左侧菜单 + 顶栏 + 内容区。
 * 屏间导航由此完成（不实现独立门户页）。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/store/app'
// 平台 logo（仅图，不跟标题文字）
import brandLogoUrl from '@/assets/logo.png'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const activeMenu = computed(() => route.path)

const menus = computed(() => {
  const items = [
    { path: '/overview', title: '产品概览', icon: 'HomeFilled' },
    { path: '/retrieval-qa', title: '检索问答', icon: 'ChatDotRound' },
    { path: '/kb/management', title: '知识库管理', icon: 'FolderOpened' },
    { path: '/model/management', title: '模型管理', icon: 'Cpu' },
    { path: '/metrics', title: '指标看板', icon: 'DataLine' },
    { path: '/permissions', title: '权限管理', icon: 'Lock' },
  ]
  if (appStore.isCommercial) {
    items.push({ path: '/commercial', title: '商业控制台', icon: 'Briefcase' })
  }
  return items
})

const pageTitle = computed(() => (route.meta.title as string) || appStore.title)

function onSelect(path: string) {
  if (path !== route.path) {
    router.push(path)
  }
}
</script>

<template>
  <el-container class="app-layout">
    <el-aside class="app-aside" :width="appStore.sidebarCollapsed ? '64px' : '220px'">
      <div class="app-brand">
        <img
          class="app-brand__logo"
          :class="{ 'app-brand__logo--compact': appStore.sidebarCollapsed }"
          :src="brandLogoUrl"
          alt="WIKI"
        />
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="appStore.sidebarCollapsed"
        router
        @select="onSelect"
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div>
          <el-button text @click="appStore.toggleSidebar">
            <el-icon><Fold v-if="!appStore.sidebarCollapsed" /><Expand v-else /></el-icon>
          </el-button>
          <strong>{{ pageTitle }}</strong>
          <el-tag class="edition-tag" size="small" effect="plain">
            {{ appStore.isCommercial ? '商业版' : '社区版' }}
          </el-tag>
        </div>
        <div class="app-header__actions">
          <el-button text type="primary" @click="router.push('/login')">登录</el-button>
          <el-button text type="primary" @click="router.push('/api-docs')">API 文档</el-button>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
