import type { RouteRecordRaw } from 'vue-router'

/**
 * 知识库功能路由（不含门户页）。
 * path 使用 kebab-case；name 使用 PascalCase。
 * 商业控制台仅商业构建注册，便于社区包剔除 views/commercial。
 */
const isCommercialBuild = import.meta.env.VITE_EDITION === 'commercial'

const layoutChildren: RouteRecordRaw[] = [
  {
    path: 'overview',
    name: 'Overview',
    component: () => import('@/views/overview/Overview.vue'),
    meta: { title: '产品概览', icon: 'HomeFilled' },
  },
  {
    path: 'kb/management',
    name: 'KbManagement',
    component: () => import('@/views/kb/KbManagement.vue'),
    meta: { title: '知识库管理', icon: 'FolderOpened' },
  },
  {
    path: 'retrieval-qa',
    name: 'RetrievalQa',
    component: () => import('@/views/chat/RetrievalQa.vue'),
    meta: { title: '检索问答', icon: 'ChatDotRound' },
  },
  {
    path: 'model/management',
    name: 'ModelManagement',
    component: () => import('@/views/model/ModelManagement.vue'),
    meta: { title: '模型管理', icon: 'Cpu' },
  },
  {
    path: 'permissions',
    name: 'Permissions',
    component: () => import('@/views/permission/Permissions.vue'),
    meta: { title: '权限管理', icon: 'Lock' },
  },
  {
    path: 'metrics',
    name: 'MetricsDashboard',
    component: () => import('@/views/metrics/MetricsDashboard.vue'),
    meta: { title: '指标看板', icon: 'DataLine' },
  },
  {
    path: 'api-docs',
    name: 'ApiDocs',
    component: () => import('@/views/docs/ApiDocs.vue'),
    meta: { title: '接口文档', public: true },
  },
]

if (isCommercialBuild) {
  layoutChildren.push({
    path: 'commercial',
    name: 'CommercialConsole',
    component: () => import('@/views/commercial/CommercialConsole.vue'),
    meta: { title: '商业控制台', icon: 'Briefcase', requiresCommercial: true },
  })
}

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/components/layout/AppLayout.vue'),
    redirect: '/retrieval-qa',
    children: layoutChildren,
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/error/NotFound.vue'),
    meta: { title: '未找到', public: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/404',
  },
]
