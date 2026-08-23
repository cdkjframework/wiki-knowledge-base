<script setup lang="ts">
/**
 * API 文档（纯 Vue 页，嵌在控制台布局内）。
 */
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE'

interface EndpointDoc {
  method: HttpMethod
  path: string
  note?: string
  params?: string[]
  body?: string
  sample?: string
  extraNotes?: string[]
  extraCode?: { label: string; lang?: string; code: string }
}

interface SectionDoc {
  id: string
  title: string
  intro?: string
  endpoints?: EndpointDoc[]
  subsections?: { title: string; endpoints: EndpointDoc[] }[]
  jsonSamples?: { label: string; code: string }[]
  listItems?: string[]
}

const baseUrl = `${window.location.protocol}//${window.location.hostname}:5000`

const toc = [
  { id: 'common', label: '通用响应结构' },
  { id: 'health', label: '1. 健康检查' },
  { id: 'session', label: '1.1 会话' },
  { id: 'query', label: '2. 查询问答' },
  { id: 'kb', label: '3. 文档管理' },
  { id: 'history', label: '4. 历史记录' },
  { id: 'model', label: '5. 模型配置管理' },
  { id: 'routes', label: '6. 前端路由' },
]

const commonOk = `{
  "total": 1,
  "code": 200,
  "data": {},
  "pageIndex": 1
}`

const commonErr = `{
  "total": 0,
  "code": 400,
  "data": {
    "error": "query is required"
  },
  "pageIndex": 1
}`

const sections: SectionDoc[] = [
  {
    id: 'common',
    title: '通用响应结构',
    intro: '除静态资源外，API 响应统一包装为：',
    jsonSamples: [
      { label: '成功示例', code: commonOk },
      { label: '错误示例', code: commonErr },
    ],
    listItems: [
      'code：HTTP 对应状态码',
      'data：实际业务数据',
      'total：结果总数（服务端按数据类型推断）',
      'pageIndex：页码，默认 1',
    ],
  },
  {
    id: 'health',
    title: '1. 健康检查',
    endpoints: [
      {
        method: 'GET',
        path: '/health',
        sample: `{
  "ok": true,
  "message": "alive"
}`,
      },
    ],
  },
  {
    id: 'session',
    title: '1.1 会话',
    intro:
      '默认使用 Redis 原子自增生成会话 ID；若 Redis 不可用，会回退到内存生成（仅保证进程内唯一）。',
    endpoints: [
      {
        method: 'GET',
        path: '/api/session',
        params: ['user_id / userId (string, 必填)'],
        sample: `{
  "ok": true,
  "user_id": "user-001",
  "session_id": "d8f4..."
}`,
      },
      {
        method: 'POST',
        path: '/api/session',
        body: `{
  "user_id": "user-001"
}`,
        sample: `{
  "ok": true,
  "user_id": "user-001",
  "session_id": "d8f4..."
}`,
      },
    ],
  },
  {
    id: 'query',
    title: '2. 查询问答',
    intro: '支持 GET /api/query 或 POST /api/query。业务接口统一前缀 /api。',
    subsections: [
      {
        title: '2.1 GET /api/query',
        endpoints: [
          {
            method: 'GET',
            path: '/api/query',
            params: [
              'query (string, 必填)',
              'k (int, 默认 2)',
              'relevance_threshold (float, 可选)',
              'model_config_id (int, 可选)',
              'model_config_name (string, 可选)',
              'use_default_model_config (bool, 默认 true)',
              'generate_answer (bool, 默认 true)',
              'deep_think (bool, 默认 false)',
              'temperature (float, 默认 0.2)',
              'max_tokens (int, 可选)',
              'user_id / userId (string, 可选)',
              'session_id / sessionId (string, 可选)',
              'stream (bool, 可选，true 启用 SSE)',
              'pageIndex (int, 可选)',
            ],
            extraNotes: [
              '模型调用仅通过数据库模型配置：优先 model_config_id，其次 model_config_name，最后默认配置。',
              'stream=true 时响应为 SSE（text/event-stream）。',
              '传入 user_id 但未传 session_id 时，服务端会生成新的 session_id。',
            ],
          },
        ],
      },
      {
        title: '2.2 POST /api/query',
        endpoints: [
          {
            method: 'POST',
            path: '/api/query',
            body: `{
  "query": "如何重置密码？",
  "k": 2,
  "generate_answer": true,
  "deep_think": false,
  "temperature": 0.2,
  "user_id": "user-001",
  "session_id": "",
  "stream": false
}`,
            sample: `{
  "answer": "...",
  "session_id": "d8f4...",
  "user_id": "user-001",
  "results": [
    {
      "filename": "account_guide.md",
      "similarity": 0.9072,
      "text": "命中分片全文...",
      "preview_text": "命中分片预览..."
    }
  ]
}`,
            extraNotes: [
              'SSE 事件：meta / thinking_delta / delta / done。',
              '启用深度思考且模型提供摘要时返回 thinking_summary。',
            ],
            extraCode: {
              label: '前端调用示例（SSE）',
              lang: 'javascript',
              code: `fetch('/api/query?stream=1', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  },
  body: JSON.stringify({
    query: '如何重置密码？',
    user_id: 'user-001',
    stream: true,
  }),
})`,
            },
          },
        ],
      },
    ],
  },
  {
    id: 'kb',
    title: '3. 文档管理',
    subsections: [
      {
        title: '3.1 新增文本文档',
        endpoints: [
          {
            method: 'POST',
            path: '/api/kb/document',
            body: `{
  "filename": "guide.md",
  "text": "文档内容"
}`,
            sample: `{
  "ok": true,
  "chunks_added": 3
}`,
          },
        ],
      },
      {
        title: '3.2 上传文件',
        endpoints: [
          {
            method: 'POST',
            path: '/api/kb/file',
            note: 'Content-Type：multipart/form-data',
            params: ['file (file, 必填)', 'filename (string, 可选)', 'encoding (string, 可选)'],
            extraNotes: ['也支持 JSON：filename + text。'],
          },
        ],
      },
      {
        title: '3.3 批量上传文件',
        endpoints: [
          {
            method: 'POST',
            path: '/api/kb/files',
            note: 'Content-Type：multipart/form-data',
            params: ['files (file, 必填，可多选)', 'encoding (string, 可选)'],
          },
        ],
      },
      {
        title: '3.4 删除单个文档',
        endpoints: [
          {
            method: 'DELETE',
            path: '/api/kb/document/{filename}',
            sample: `{
  "ok": true,
  "chunks_removed": 5
}`,
          },
        ],
      },
      {
        title: '3.5 获取文档列表',
        endpoints: [
          {
            method: 'GET',
            path: '/api/kb/documents',
            sample: `{
  "ok": true,
  "count": 2,
  "documents": [
    { "filename": "guide.md", "chunk_count": 3, "char_count": 1200 }
  ]
}`,
          },
        ],
      },
      {
        title: '3.6 获取知识库统计',
        endpoints: [
          {
            method: 'GET',
            path: '/api/stats',
            sample: `{
  "ok": true,
  "stats": {
    "document_count": 2,
    "chunk_count": 8,
    "dimension": 1024
  }
}`,
          },
        ],
      },
      {
        title: '3.7 清空知识库',
        endpoints: [
          {
            method: 'DELETE',
            path: '/api/kb',
            sample: `{
  "ok": true
}`,
          },
        ],
      },
      {
        title: '3.8 获取分片列表',
        endpoints: [
          {
            method: 'GET',
            path: '/api/kb/chunks',
            params: [
              'pageIndex (int, 可选，默认 1)',
              'pageSize (int, 可选，默认 20)',
              'filename (string, 可选)',
              'q (string, 可选，关键词搜索)',
            ],
            sample: `{
  "ok": true,
  "count": 2,
  "chunks": [
    { "id": 0, "filename": "guide.md", "text": "...", "char_count": 320 }
  ]
}`,
          },
        ],
      },
      {
        title: '3.9 修改分片',
        endpoints: [
          {
            method: 'PUT',
            path: '/api/kb/chunk/{id}',
            body: `{
  "text": "更新后的分片内容"
}`,
            sample: `{
  "ok": true
}`,
          },
        ],
      },
      {
        title: '3.10 删除分片',
        endpoints: [
          {
            method: 'DELETE',
            path: '/api/kb/chunk/{id}',
            sample: `{
  "ok": true
}`,
          },
        ],
      },
      {
        title: '3.11 重建文件分片',
        endpoints: [
          {
            method: 'POST',
            path: '/api/kb/chunks/rebuild',
            body: `{
  "filename": "guide.md"
}`,
            sample: `{
  "ok": true,
  "chunks_added": 3
}`,
          },
        ],
      },
    ],
  },
  {
    id: 'history',
    title: '4. 历史记录',
    subsections: [
      {
        title: '4.1 查询历史',
        endpoints: [
          {
            method: 'GET',
            path: '/api/history',
            params: [
              'limit (int, 可选)',
              'action (string, 可选)',
              'group_by_session (bool, 可选)',
              'pageIndex (int, 可选)',
            ],
            extraNotes: ['group_by_session=true 时返回 sessions，否则返回 history。'],
          },
        ],
      },
      {
        title: '4.2 清空历史',
        endpoints: [
          {
            method: 'DELETE',
            path: '/api/history',
            sample: `{
  "ok": true,
  "removed": 12
}`,
          },
        ],
      },
      {
        title: '4.3 删除单条历史',
        endpoints: [
          {
            method: 'DELETE',
            path: '/api/history/{id}',
            sample: `{
  "ok": true,
  "removed": 1
}`,
          },
        ],
      },
      {
        title: '4.4 删除整个会话',
        endpoints: [
          {
            method: 'DELETE',
            path: '/api/session/{session_id}',
            sample: `{
  "ok": true,
  "removed": 1
}`,
          },
        ],
      },
    ],
  },
  {
    id: 'model',
    title: '5. 模型配置管理',
    intro: '以下接口依赖数据库后端；若未启用数据库，接口会返回不可用提示。',
    subsections: [
      {
        title: '5.1 获取 Provider 列表',
        endpoints: [{ method: 'GET', path: '/api/model/providers' }],
      },
      {
        title: '5.2 查询配置列表',
        endpoints: [
          {
            method: 'GET',
            path: '/api/model/configs',
            params: ['provider / is_active / model_type（均可选）'],
          },
        ],
      },
      {
        title: '5.3 新增配置',
        endpoints: [
          {
            method: 'POST',
            path: '/api/model/config',
            note: '必填：name、provider、base_url、model_name',
          },
        ],
      },
      {
        title: '5.4 查询 / 更新 / 删除配置',
        endpoints: [
          { method: 'GET', path: '/api/model/config/{id_or_name}' },
          { method: 'PUT', path: '/api/model/config/{id}' },
          { method: 'DELETE', path: '/api/model/config/{id}' },
        ],
      },
      {
        title: '5.5 默认配置 / 测试 / 初始化预设',
        endpoints: [
          { method: 'GET', path: '/api/model/config/default' },
          { method: 'POST', path: '/api/model/config/{id}/default' },
          { method: 'POST', path: '/api/model/config/test' },
          { method: 'POST', path: '/api/model/config/bootstrap' },
        ],
      },
    ],
  },
  {
    id: 'routes',
    title: '6. 前端路由',
    listItems: [
      'GET / ：控制台首页（SPA）',
      'GET /retrieval-qa ：检索问答',
      'GET /kb/management ：知识库管理',
      'GET /model/management ：模型管理',
      'GET /api-docs ：本 API 文档页',
      'GET /assets/* ：静态资源',
      'GET /health 或 /api/health ：探活',
    ],
  },
]

function methodClass(method: HttpMethod) {
  return `method method--${method.toLowerCase()}`
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <div class="api-docs">
    <header class="api-docs__hero page-card">
      <h1>API 文档</h1>
      <p>接口一览与请求示例，便于本地调试和业务集成。业务路径统一前缀 <code>/api</code>。</p>
      <div class="api-docs__meta">
        <span class="api-docs__pill">Base URL</span>
        <code>{{ baseUrl }}</code>
      </div>
    </header>

    <div class="api-docs__layout">
      <aside class="api-docs__toc page-card">
        <h2>目录</h2>
        <button
          v-for="item in toc"
          :key="item.id"
          type="button"
          class="api-docs__toc-link"
          @click="scrollTo(item.id)"
        >
          {{ item.label }}
        </button>
      </aside>

      <article class="api-docs__doc">
        <section v-for="sec in sections" :id="sec.id" :key="sec.id" class="page-card api-docs__section">
          <h2>{{ sec.title }}</h2>
          <p v-if="sec.intro" class="api-docs__note">{{ sec.intro }}</p>

          <template v-if="sec.jsonSamples?.length">
            <div v-for="(sample, idx) in sec.jsonSamples" :key="idx" class="api-docs__block">
              <div class="api-docs__label">{{ sample.label }}</div>
              <pre><code>{{ sample.code }}</code></pre>
            </div>
          </template>

          <ul v-if="sec.listItems?.length">
            <li v-for="(item, idx) in sec.listItems" :key="idx">{{ item }}</li>
          </ul>

          <template v-if="sec.endpoints?.length">
            <div v-for="(ep, idx) in sec.endpoints" :key="idx" class="api-docs__endpoint">
              <div class="api-docs__endpoint-head">
                <span :class="methodClass(ep.method)">{{ ep.method }}</span>
                <span class="api-docs__path">{{ ep.path }}</span>
              </div>
              <p v-if="ep.note" class="api-docs__note">{{ ep.note }}</p>
              <template v-if="ep.params?.length">
                <div class="api-docs__label">参数</div>
                <ul>
                  <li v-for="(p, pidx) in ep.params" :key="pidx"><code>{{ p }}</code></li>
                </ul>
              </template>
              <template v-if="ep.body">
                <div class="api-docs__label">请求体</div>
                <pre><code>{{ ep.body }}</code></pre>
              </template>
              <template v-if="ep.sample">
                <div class="api-docs__label">data 示例</div>
                <pre><code>{{ ep.sample }}</code></pre>
              </template>
              <p v-for="(n, nidx) in ep.extraNotes || []" :key="nidx" class="api-docs__note">{{ n }}</p>
              <template v-if="ep.extraCode">
                <div class="api-docs__label">{{ ep.extraCode.label }}</div>
                <pre><code>{{ ep.extraCode.code }}</code></pre>
              </template>
            </div>
          </template>

          <template v-if="sec.subsections?.length">
            <div v-for="(sub, sidx) in sec.subsections" :key="sidx" class="api-docs__subsection">
              <h3>{{ sub.title }}</h3>
              <div v-for="(ep, idx) in sub.endpoints" :key="idx" class="api-docs__endpoint">
                <div class="api-docs__endpoint-head">
                  <span :class="methodClass(ep.method)">{{ ep.method }}</span>
                  <span class="api-docs__path">{{ ep.path }}</span>
                </div>
                <p v-if="ep.note" class="api-docs__note">{{ ep.note }}</p>
                <template v-if="ep.params?.length">
                  <div class="api-docs__label">参数</div>
                  <ul>
                    <li v-for="(p, pidx) in ep.params" :key="pidx"><code>{{ p }}</code></li>
                  </ul>
                </template>
                <template v-if="ep.body">
                  <div class="api-docs__label">请求体</div>
                  <pre><code>{{ ep.body }}</code></pre>
                </template>
                <template v-if="ep.sample">
                  <div class="api-docs__label">data 示例</div>
                  <pre><code>{{ ep.sample }}</code></pre>
                </template>
                <p v-for="(n, nidx) in ep.extraNotes || []" :key="nidx" class="api-docs__note">{{ n }}</p>
                <template v-if="ep.extraCode">
                  <div class="api-docs__label">{{ ep.extraCode.label }}</div>
                  <pre><code>{{ ep.extraCode.code }}</code></pre>
                </template>
              </div>
            </div>
          </template>
        </section>
      </article>
    </div>
  </div>
</template>

<style scoped>
.api-docs {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.api-docs__hero h1 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
}

.api-docs__hero p {
  margin: 0 0 12px;
  color: var(--color-text-secondary);
}

.api-docs__meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-radius: 8px;
  background: var(--color-primary-subtle);
  border: 1px solid var(--color-border);
}

.api-docs__pill {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-link);
}

.api-docs__layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 16px;
  align-items: start;
}

.api-docs__toc h2 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.api-docs__toc-link {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--color-text-primary);
  font: inherit;
  font-size: 13px;
  padding: 6px 8px;
  margin: 0 -8px;
  border-radius: 6px;
  cursor: pointer;
}

.api-docs__toc-link:hover {
  color: var(--color-link);
  background: var(--color-primary-subtle);
}

.api-docs__section {
  margin-bottom: 16px;
  scroll-margin-top: 16px;
}

.api-docs__section h2 {
  margin: 0 0 12px;
  font-size: 18px;
}

.api-docs__section h3 {
  margin: 16px 0 10px;
  font-size: 15px;
}

.api-docs__note {
  margin: 0 0 10px;
  color: var(--color-text-tertiary);
  font-size: 13px;
  line-height: 1.6;
}

.api-docs__label {
  margin: 8px 0 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.api-docs__endpoint {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
  border-radius: 10px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border);
}

.api-docs__endpoint-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.api-docs__path {
  font-family: 'Cascadia Mono', Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
}

.method {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
}

.method--get {
  background: var(--color-success);
}

.method--post {
  background: #3b5bdb;
}

.method--put {
  background: var(--color-primary);
}

.method--delete {
  background: var(--color-danger);
}

.api-docs ul {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-secondary);
}

.api-docs pre {
  margin: 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #0a2540;
  color: #e8eef5;
  overflow-x: auto;
  border: 1px solid var(--color-border-strong);
}

.api-docs code {
  font-family: 'Cascadia Mono', Consolas, monospace;
  font-size: 12.5px;
}

.api-docs p code,
.api-docs li code,
.api-docs__meta code {
  background: var(--color-primary-subtle);
  color: var(--color-link);
  padding: 1px 6px;
  border-radius: 4px;
}

.api-docs pre code {
  background: transparent;
  color: inherit;
  padding: 0;
}

@media (max-width: 900px) {
  .api-docs__layout {
    grid-template-columns: 1fr;
  }
}
</style>
