<script setup lang="ts">
/**
 * 商业版管理控制台：左侧分组目录 + 右侧功能区（11 面板）。
 * 仅商业构建可见；面板为产品示意 UI，后端 commercial API 后续接入。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

type PanelId =
  | 'license'
  | 'multi-tenant'
  | 'rbac'
  | 'audit'
  | 'encryption'
  | 'mcp'
  | 'web-search'
  | 'connectors'
  | 'snapshots'
  | 'web-import'
  | 'incremental'
  | 'backup'

interface NavItem {
  id: PanelId
  title: string
  kb?: string
  dual?: boolean
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const groups: NavGroup[] = [
  {
    label: '许可',
    items: [{ id: 'license', title: 'License 管理' }],
  },
  {
    label: '安全与治理',
    items: [
      { id: 'multi-tenant', title: '多租户隔离', kb: 'KB-03' },
      { id: 'rbac', title: 'RBAC 角色权限', kb: 'KB-04' },
      { id: 'audit', title: '审计日志', kb: 'KB-05' },
      { id: 'encryption', title: '密钥与加密', kb: 'KB-06' },
    ],
  },
  {
    label: '集成扩展',
    items: [
      { id: 'mcp', title: 'MCP 端点配置', kb: 'KB-07' },
      { id: 'web-search', title: '网络搜索', kb: 'KB-10' },
      { id: 'connectors', title: '连接器管理', kb: 'KB-09' },
    ],
  },
  {
    label: '数据治理',
    items: [
      { id: 'snapshots', title: '版本化快照', kb: 'KB-14' },
      { id: 'web-import', title: '网页导入增强', kb: 'KB-08*', dual: true },
      { id: 'incremental', title: '增量更新', kb: 'KB-13*', dual: true },
      { id: 'backup', title: '加密备份', kb: 'KB-15*', dual: true },
    ],
  },
]

const active = ref<PanelId>('license')

const activeMeta = computed(() => {
  for (const g of groups) {
    const hit = g.items.find((i) => i.id === active.value)
    if (hit) return hit
  }
  return groups[0].items[0]
})

const tenants = [
  { name: 'acme-prod', id: 'tn_01', docs: 1280, storage: '4.2 GB', quota: '62%', check: '通过' },
  { name: 'beta-lab', id: 'tn_02', docs: 86, storage: '310 MB', quota: '18%', check: '通过' },
  { name: 'demo', id: 'tn_03', docs: 12, storage: '28 MB', quota: '5%', check: '通过' },
]

const roles = [
  { name: '租户管理员', desc: '全权限，仅限本租户', users: 2 },
  { name: '编辑者', desc: '导入与编辑文档', users: 8 },
  { name: '查看者', desc: '只读检索', users: 24 },
  { name: 'API 调用方', desc: '凭证访问 /query', users: 3 },
]

const audits = [
  { time: '2026-08-20 21:02:11', actor: 'admin', action: '更新 License', resource: 'license', tenant: '-', result: '成功' },
  { time: '2026-08-20 20:47:09', actor: 'zhang.wei', action: '删除', resource: 'kb-old-archive', tenant: 'beta', result: '拒绝（RBAC）' },
  { time: '2026-08-20 19:15:33', actor: 'api-bot', action: 'query', resource: '/query', tenant: 'acme-prod', result: '成功' },
]

const connectors = [
  { name: 'Confluence', status: '已连接', lastSync: '2 小时前' },
  { name: 'SharePoint', status: '未配置', lastSync: '—' },
  { name: '本地 OCR', status: '就绪', lastSync: '今日' },
]

const snapshots = [
  { snapId: 'snap_20260820', docCount: 1280, createdAt: '2026-08-20 18:00', diskSize: '1.1 GB' },
  { snapId: 'snap_20260813', docCount: 1204, createdAt: '2026-08-13 18:00', diskSize: '1.0 GB' },
]

function toastSoon(name: string) {
  ElMessage.info(`${name}：示意操作，商业后端接入后生效`)
}
</script>

<template>
  <div class="comm-shell">
    <aside class="comm-nav page-card">
      <div class="comm-nav__title">商业版功能</div>
      <div v-for="group in groups" :key="group.label" class="comm-group">
        <div class="comm-group__label">{{ group.label }}</div>
        <button
          v-for="item in group.items"
          :key="item.id"
          type="button"
          class="comm-item"
          :class="{ active: active === item.id }"
          @click="active = item.id"
        >
          <span>{{ item.title }}</span>
          <span v-if="item.dual" class="dual-dot" title="双版增强" />
          <span v-if="item.kb" class="kb-id">{{ item.kb }}</span>
        </button>
      </div>
    </aside>

    <section class="comm-main page-card">
      <header class="panel-head">
        <h1>{{ activeMeta.title }}</h1>
        <p>商业版独立产物管理界面示意。当前为前端壳层，不绑定真实 license 校验接口。</p>
        <div class="panel-meta">
          <el-tag v-if="activeMeta.kb" size="small" effect="plain">{{ activeMeta.kb }}</el-tag>
          <el-tag size="small" type="success" effect="plain">商业版</el-tag>
        </div>
      </header>

      <!-- License -->
      <div v-if="active === 'license'" class="panel-body">
        <div class="license-row">
          <div class="license-status">
            <span class="dot ok" />
            <strong>License 有效</strong>
          </div>
          <div class="fields">
            <div><span class="label">计划</span><div>Commercial</div></div>
            <div><span class="label">到期</span><div>2027-08-20</div></div>
            <div>
              <span class="label">License Key</span>
              <div><code>WIKI-COMM-****-2027</code></div>
            </div>
          </div>
        </div>
        <div class="usage-grid">
          <div class="usage">
            <div class="usage__head"><span>活跃租户</span><b>3 / 10</b></div>
            <el-progress :percentage="30" :show-text="false" />
          </div>
          <div class="usage">
            <div class="usage__head"><span>API 调用（月）</span><b>42k / 100k</b></div>
            <el-progress :percentage="42" :show-text="false" />
          </div>
          <div class="usage">
            <div class="usage__head"><span>存储</span><b>4.5 / 50 GB</b></div>
            <el-progress :percentage="9" :show-text="false" />
          </div>
        </div>
        <el-form inline style="margin-top: 16px" @submit.prevent>
          <el-form-item label="替换 Key">
            <el-input placeholder="粘贴新的 License Key" style="width: 280px" />
          </el-form-item>
          <el-button type="primary" @click="toastSoon('更新 License')">更新</el-button>
        </el-form>
      </div>

      <!-- 多租户 -->
      <div v-else-if="active === 'multi-tenant'" class="panel-body">
        <div class="toolbar">
          <el-button type="primary" @click="toastSoon('新建租户')">+ 新建租户</el-button>
          <el-button @click="toastSoon('导出租户')">导出租户清单</el-button>
        </div>
        <el-table :data="tenants" border>
          <el-table-column prop="name" label="租户名" />
          <el-table-column prop="id" label="空间 ID" width="100" />
          <el-table-column prop="docs" label="文档数" width="90" />
          <el-table-column prop="storage" label="存储" width="100" />
          <el-table-column prop="quota" label="API 配额" width="100" />
          <el-table-column prop="check" label="隔离校验" width="100" />
        </el-table>
        <p class="note">隔离：索引按 tenant_id 分区 · 文档路径隔离 · 检索强制校验</p>
      </div>

      <!-- RBAC -->
      <div v-else-if="active === 'rbac'" class="panel-body">
        <div class="toolbar">
          <el-button type="primary" @click="toastSoon('新建角色')">+ 新建角色</el-button>
        </div>
        <el-table :data="roles" border>
          <el-table-column prop="name" label="角色" width="140" />
          <el-table-column prop="desc" label="说明" />
          <el-table-column prop="users" label="成员数" width="90" />
          <el-table-column label="操作" width="120">
            <template #default>
              <el-button link type="primary" @click="toastSoon('编辑角色')">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p class="note">粒度：知识库 / 文档夹 / 单文档 · API 调用方独立轨道</p>
      </div>

      <!-- 审计 -->
      <div v-else-if="active === 'audit'" class="panel-body">
        <div class="toolbar">
          <el-button @click="toastSoon('导出审计')">导出 CSV</el-button>
        </div>
        <el-table :data="audits" border>
          <el-table-column prop="time" label="时间" width="170" />
          <el-table-column prop="actor" label="操作人" width="110" />
          <el-table-column prop="action" label="操作" width="120" />
          <el-table-column prop="resource" label="资源" />
          <el-table-column prop="tenant" label="租户" width="100" />
          <el-table-column prop="result" label="结果" width="120" />
        </el-table>
      </div>

      <!-- 加密 -->
      <div v-else-if="active === 'encryption'" class="panel-body">
        <el-form label-width="120px" style="max-width: 520px">
          <el-form-item label="静态加密">
            <el-switch model-value />
          </el-form-item>
          <el-form-item label="密钥提供方">
            <el-select model-value="local" style="width: 220px">
              <el-option label="本地密钥库" value="local" />
              <el-option label="KMS（示意）" value="kms" />
            </el-select>
          </el-form-item>
          <el-form-item label="轮换周期">
            <el-input model-value="90 天" style="width: 220px" />
          </el-form-item>
          <el-button type="primary" @click="toastSoon('保存加密策略')">保存策略</el-button>
        </el-form>
      </div>

      <!-- MCP -->
      <div v-else-if="active === 'mcp'" class="panel-body">
        <el-form label-position="top" style="max-width: 560px">
          <el-form-item label="MCP 服务端点">
            <el-input model-value="http://127.0.0.1:3100/mcp" />
          </el-form-item>
          <el-form-item label="协议">
            <el-radio-group model-value="http">
              <el-radio value="http">HTTP</el-radio>
              <el-radio value="stdio">stdio</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-button type="primary" @click="toastSoon('保存 MCP')">保存</el-button>
          <el-button @click="toastSoon('探测 MCP')">探测连通性</el-button>
        </el-form>
      </div>

      <!-- 网络搜索 -->
      <div v-else-if="active === 'web-search'" class="panel-body">
        <el-alert
          type="info"
          :closable="false"
          title="网络搜索增强"
          description="为问答补充公网检索结果（示意）。默认关闭，需显式启用。"
          style="margin-bottom: 16px"
        />
        <el-form label-width="100px">
          <el-form-item label="启用">
            <el-switch />
          </el-form-item>
          <el-form-item label="提供商">
            <el-select placeholder="选择提供商" style="width: 220px">
              <el-option label="内置聚合（示意）" value="builtin" />
            </el-select>
          </el-form-item>
        </el-form>
      </div>

      <!-- 连接器 -->
      <div v-else-if="active === 'connectors'" class="panel-body">
        <el-table :data="connectors" border>
          <el-table-column prop="name" label="连接器" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="lastSync" label="最近同步" width="140" />
          <el-table-column label="操作" width="160">
            <template #default>
              <el-button link type="primary" @click="toastSoon('配置连接器')">配置</el-button>
              <el-button link @click="toastSoon('同步连接器')">同步</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 快照 -->
      <div v-else-if="active === 'snapshots'" class="panel-body">
        <div class="toolbar">
          <el-button type="primary" @click="toastSoon('创建快照')">创建快照</el-button>
        </div>
        <el-table :data="snapshots" border>
          <el-table-column prop="snapId" label="快照 ID" />
          <el-table-column prop="docCount" label="文档数" width="100" />
          <el-table-column prop="createdAt" label="时间" width="170" />
          <el-table-column prop="diskSize" label="大小" width="100" />
          <el-table-column label="操作" width="160">
            <template #default>
              <el-button link type="primary" @click="toastSoon('回滚快照')">回滚</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 网页导入 -->
      <div v-else-if="active === 'web-import'" class="panel-body">
        <el-form label-position="top" style="max-width: 560px">
          <el-form-item label="URL">
            <el-input placeholder="https://example.com/docs" />
          </el-form-item>
          <el-form-item label="深度">
            <el-input-number :model-value="2" :min="1" :max="5" />
          </el-form-item>
          <el-button type="primary" @click="toastSoon('网页导入')">开始导入</el-button>
        </el-form>
        <p class="note">双版增强能力：商业版提供更深层爬取与站点规则。</p>
      </div>

      <!-- 增量 -->
      <div v-else-if="active === 'incremental'" class="panel-body">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="增量策略">按文件哈希跳过未变更文档</el-descriptions-item>
          <el-descriptions-item label="上次增量">2026-08-20 22:10 · +36 分片</el-descriptions-item>
          <el-descriptions-item label="调度">每日 02:00（示意）</el-descriptions-item>
        </el-descriptions>
        <el-button style="margin-top: 14px" type="primary" @click="toastSoon('立即增量')">立即执行增量</el-button>
      </div>

      <!-- 备份 -->
      <div v-else-if="active === 'backup'" class="panel-body">
        <el-form label-width="110px" style="max-width: 520px">
          <el-form-item label="备份目标">
            <el-input model-value="/var/backups/wiki-kb" />
          </el-form-item>
          <el-form-item label="加密备份">
            <el-switch model-value />
          </el-form-item>
          <el-form-item label="保留份数">
            <el-input-number :model-value="7" :min="1" :max="30" />
          </el-form-item>
          <el-button type="primary" @click="toastSoon('立即备份')">立即备份</el-button>
        </el-form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.comm-shell {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  min-height: calc(100vh - 120px);
}
.comm-nav {
  padding: 12px 0;
  position: sticky;
  top: 12px;
}
.comm-nav__title {
  padding: 4px 20px 12px;
  font-weight: 700;
  font-size: 14px;
}
.comm-group {
  margin-bottom: 14px;
}
.comm-group__label {
  padding: 0 20px 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.comm-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  background: transparent;
  padding: 9px 20px;
  text-align: left;
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: 14px;
  border-left: 3px solid transparent;
}
.comm-item:hover {
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
}
.comm-item.active {
  background: var(--color-primary-subtle);
  color: var(--color-link);
  font-weight: 600;
  border-left-color: var(--color-primary);
}
.kb-id {
  margin-left: auto;
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-weight: 400;
}
.comm-item.active .kb-id {
  color: var(--color-link);
}
.dual-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-warning);
  flex-shrink: 0;
}
.panel-head h1 {
  margin: 0 0 6px;
  font-size: 22px;
}
.panel-head p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
  max-width: 640px;
}
.panel-meta {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.panel-body {
  margin-top: 18px;
}
.license-row {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: center;
  margin-bottom: 18px;
}
.license-status {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dot.ok {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-success);
}
.fields {
  display: flex;
  gap: 28px;
  flex-wrap: wrap;
  margin-left: auto;
}
.fields .label {
  display: block;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.fields code {
  font-size: 13px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 2px 6px;
}
.usage-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.usage__head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 13px;
}
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
.note {
  margin-top: 12px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
@media (max-width: 960px) {
  .comm-shell,
  .usage-grid {
    grid-template-columns: 1fr;
  }
  .comm-nav {
    position: static;
  }
}
</style>
