import { createRouter, createWebHistory } from 'vue-router'
import { routes } from './routes'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'

NProgress.configure({ showSpinner: false })

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to, _from, next) => {
  NProgress.start()
  const edition = import.meta.env.VITE_EDITION || 'community'
  if (to.meta.requiresCommercial && edition !== 'commercial') {
    next({ name: 'Overview' })
    return
  }
  next()
})

router.afterEach(() => {
  NProgress.done()
})

export default router
