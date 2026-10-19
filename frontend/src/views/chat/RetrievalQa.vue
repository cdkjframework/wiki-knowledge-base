<script setup lang="ts">
/**
 * 检索问答：左侧会话历史、SSE 流式回答、深度思考开关（默认关）、引用来源。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, Delete, Refresh, Select } from '@element-plus/icons-vue'
import { createSession, streamQuery, type SourceResult } from '@/api/query'
import {
  deleteHistorySession,
  listHistorySessions,
  type HistoryItem,
  type HistorySession,
} from '@/api/history'
import { getKbSettings } from '@/api/kb'
import { listModelConfigs, type ModelConfig } from '@/api/model'
import { loadSessionId, loadUserId, saveSessionId, saveUserId } from '@/utils/session'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  thinkingSummary?: string
  sources?: SourceResult[]
  pending?: boolean
}

const messages = ref<ChatMessage[]>([])
const input = ref('')
const userId = ref(loadUserId())
const sessionId = ref(loadSessionId())
/** 初始占位；挂载后从 KB-20 配置同步 default_k */
const k = ref(5)
const kMax = ref(20)
/** 候选过滤线：只读，取自「知识库管理 → 检索与分片」（库内配置） */
const minSimilarity = ref(0.6)
const deepThink = ref(false)
/** 空字符串表示走默认模型配置 */
const modelConfigId = ref<string>('')
const modelConfigs = ref<ModelConfig[]>([])
const sending = ref(false)
const sources = ref<SourceResult[]>([])
/** 模型已明确「无法确定」时，侧栏只当候选看，不当作已证实依据 */
const sourcesInsufficient = ref(false)
const sourcesExpanded = ref(true)
const abortRef = ref<AbortController | null>(null)
/** 刚复制成功的消息 id，用于图标短暂变成勾 */
const copiedId = ref('')
let copiedTimer: ReturnType<typeof setTimeout> | null = null

const listRef = ref<HTMLElement | null>(null)
const historySessions = ref<HistorySession[]>([])
const historyLoading = ref(false)

const canSend = computed(() => input.value.trim().length > 0 && userId.value.trim().length > 0 && !sending.value)

/** 左侧列表：排除系统检索写入；优先当前用户 */
const visibleSessions = computed(() => {
  const uid = userId.value.trim()
  const list = historySessions.value.filter((s) => {
    const sid = String(s.session_id || '')
    // history_store 无 session 时会写成 system_query_*，那是检索旁路不是聊天
    if (sid.startsWith('system_')) return false
    return true
  })
  if (!uid) return list
  const mine = list.filter((s) => !s.user_id || s.user_id === uid)
  return mine.length ? mine : list
})

function sessionTitle(session: HistorySession) {
  const raw = String(session.first_query || '').trim()
  if (!raw) return '未命名会话'
  return raw.length > 36 ? `${raw.slice(0, 36)}…` : raw
}

function isInsufficientAnswer(text: string) {
  const t = String(text || '').trim()
  if (!t) return false
  return /根据当前知识库无法确定|知识库没有足够依据|未检索到相关知识库内容|无法确定答案/.test(t)
}

function finiteOrNull(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

// 主标签只给名次和判定状态：综合分没校准过，写成 0.87、1.00 这种数字用户会当成「正确率」
function sourceScoreText(item: SourceResult) {
  const rank = Number(item.rank)
  const parts: string[] = []
  if (Number.isFinite(rank) && rank > 0) parts.push(`#${rank}`)
  if (item.evidence?.passed !== false) parts.push('已通过证据判定')
  return parts.length ? parts.join(' · ') : '-'
}

// 诊断行按通道分开写，缺哪项就不显示；BM25 是原始词法分，量纲和余弦不同
function sourceScoreDetail(item: SourceResult) {
  const bits: string[] = []
  const vector = finiteOrNull(item.vector_similarity ?? item.embed_similarity)
  const bm25 = finiteOrNull(item.bm25_score)
  const rerank = finiteOrNull(item.rerank_similarity)
  if (vector !== null) bits.push(`向量 ${vector.toFixed(2)}`)
  if (bm25 !== null) bits.push(`BM25 ${bm25.toFixed(2)}`)
  if (rerank !== null) bits.push(`重排 ${rerank.toFixed(2)}`)
  if (item.rerank_status === 'failed') bits.push('重排失败')
  if (!bits.length) return ''
  return `${bits.join(' · ')}（内部排序分，非正确率）`
}

function sourceTagType(item: SourceResult) {
  if (sourcesInsufficient.value) return 'info'
  return item.evidence?.passed === false ? 'info' : 'success'
}

function applySourcesInsufficientFromAnswer(answer: string) {
  const bad = isInsufficientAnswer(answer)
  sourcesInsufficient.value = bad
  // 答不出时默认收起来，避免「引用 4 条 + 高匹配」造成误解
  if (bad && sources.value.length) {
    sourcesExpanded.value = false
  }
}

/** 还原助手正文：answer → messages 末条 → 检索片段（仅检索未生成时） */
function resolveHistoryAnswer(item: HistoryItem): string {
  const resp = item.response || {}
  const ans = String(resp.answer || '').trim()
  if (ans) return ans

  const msgs = resp.messages
  if (Array.isArray(msgs)) {
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      if (msgs[i]?.role !== 'assistant') continue
      const c = String(msgs[i]?.content || '').trim()
      if (c) return c
    }
  }

  const results = resp.results || []
  if (!results.length) return ''

  // 仅检索（未要模型回答）时，把命中原文拼出来，避免「有引用却空白」
  const retrievalOnly =
    resp.finish_reason === 'not_requested' || item.request?.generate_answer === false
  const chunks = results.slice(0, retrievalOnly ? 3 : 1).map((r, i) => {
    const name = String(r.filename || `来源 ${i + 1}`).trim()
    const body = String(r.preview_text || r.text || '').trim()
    if (!body) return `【${name}】`
    return `【${name}】\n${body}`
  })
  return chunks.filter(Boolean).join('\n\n')
}

function formatSessionTime(ts?: string) {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 16)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function refreshHistory() {
  historyLoading.value = true
  try {
    const data = await listHistorySessions({ limit: 50, action: 'query' })
    historySessions.value = data.sessions || []
  } catch {
    historySessions.value = []
  } finally {
    historyLoading.value = false
  }
}

/** 点击左侧记录：把该会话全部问答还原到主界面 */
async function openSession(session: HistorySession) {
  if (sending.value) {
    ElMessage.warning('请先停止当前生成')
    return
  }
  abortRef.value?.abort()
  const sid = String(session.session_id || '').trim()
  if (!sid) return

  sessionId.value = sid
  saveSessionId(sid)
  if (session.user_id) {
    userId.value = String(session.user_id)
    saveUserId(userId.value)
  }

  const items = [...(session.items || [])].sort(
    (a, b) => Number(a.id || 0) - Number(b.id || 0),
  )
  const msgs: ChatMessage[] = []
  let lastSources: SourceResult[] = []

  for (const item of items) {
    if (item.action && item.action !== 'query') continue
    const q = String(item.request?.query || '').trim()
    const ans = resolveHistoryAnswer(item)
    const thinking = String(item.response?.thinking || '')
    const thinkingSummary = String(
      item.response?.thinking_summary || item.thinking_summary || '',
    )
    const results = (item.response?.results || []) as SourceResult[]
    if (q) {
      msgs.push({ id: `h-u-${item.id ?? uid()}`, role: 'user', content: q })
    }
    if (ans || results.length || thinking) {
      msgs.push({
        id: `h-a-${item.id ?? uid()}`,
        role: 'assistant',
        content: ans || '（无回答内容）',
        thinking: thinking || undefined,
        thinkingSummary: thinkingSummary || undefined,
        sources: results,
      })
      if (results.length) lastSources = results
    }
  }

  messages.value = msgs
  sources.value = lastSources
  const lastAssistant = [...msgs].reverse().find((m) => m.role === 'assistant')
  applySourcesInsufficientFromAnswer(String(lastAssistant?.content || ''))
  if (!sourcesInsufficient.value) sourcesExpanded.value = true
  await scrollToBottom()
}

async function removeSession(session: HistorySession, ev: Event) {
  ev.stopPropagation()
  const sid = String(session.session_id || '').trim()
  if (!sid) return
  try {
    await ElMessageBox.confirm('删除该会话的全部聊天记录？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteHistorySession(sid)
    if (sessionId.value === sid) {
      newChat()
    }
    await refreshHistory()
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.error((err as Error).message || '删除失败')
  }
}

function uid() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function scrollToBottom() {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

async function ensureSession(): Promise<string> {
  saveUserId(userId.value)
  if (sessionId.value.trim()) return sessionId.value.trim()
  const sid = await createSession(userId.value.trim())
  sessionId.value = sid
  saveSessionId(sid)
  return sid
}

function newChat() {
  abortRef.value?.abort()
  messages.value = []
  sources.value = []
  sourcesInsufficient.value = false
  sourcesExpanded.value = true
  sessionId.value = ''
  saveSessionId('')
  void refreshHistory()
}

async function send() {
  const query = input.value.trim()
  if (!canSend.value) {
    if (!userId.value.trim()) ElMessage.warning('请填写用户 ID')
    return
  }

  sending.value = true
  input.value = ''
  const sid = await ensureSession().catch((err: Error) => {
    ElMessage.error(err.message || '创建会话失败')
    sending.value = false
    return ''
  })
  if (!sid) return

  messages.value.push({ id: uid(), role: 'user', content: query })
  const assistantId = uid()
  messages.value.push({
    id: assistantId,
    role: 'assistant',
    content: '',
    thinking: '',
    pending: true,
    sources: [],
  })
  sources.value = []
  sourcesInsufficient.value = false
  sourcesExpanded.value = true
  await scrollToBottom()

  /** 必须改 messages 里的那一项，直接改局部对象 Vue 不重渲染 */
  function patchAssistant(patch: Partial<ChatMessage>) {
    const idx = messages.value.findIndex((m) => m.id === assistantId)
    if (idx < 0) return
    const cur = messages.value[idx]
    messages.value[idx] = { ...cur, ...patch }
  }

  function appendAssistant(field: 'content' | 'thinking', delta: string) {
    const idx = messages.value.findIndex((m) => m.id === assistantId)
    if (idx < 0) return
    const cur = messages.value[idx]
    messages.value[idx] = { ...cur, [field]: `${cur[field] || ''}${delta}` }
  }

  const controller = new AbortController()
  abortRef.value = controller

  try {
    const body: Parameters<typeof streamQuery>[0] = {
      query,
      k: k.value,
      deep_think: deepThink.value,
      user_id: userId.value.trim(),
      session_id: sid,
      generate_answer: true,
      min_source_similarity: minSimilarity.value > 0 ? minSimilarity.value : 0,
    }
    if (modelConfigId.value) {
      body.model_config_id = Number(modelConfigId.value)
      body.use_default_model_config = false
    } else {
      body.use_default_model_config = true
    }
    await streamQuery(body, {
      signal: controller.signal,
      onMeta: (payload) => {
        // 服务端判定无可靠证据时不展示任何来源卡片
        const candidates = payload.evidence_status === 'insufficient' ? [] : payload.results || []
        const refs = candidates.filter((item) => {
          if (minSimilarity.value <= 0) return true
          const sim = Number(item.similarity)
          return Number.isFinite(sim) && sim >= minSimilarity.value
        })
        patchAssistant({ sources: refs })
        sources.value = refs
        if (payload.session_id) {
          sessionId.value = String(payload.session_id)
          saveSessionId(sessionId.value)
        }
      },
      onDelta: (delta) => {
        appendAssistant('content', delta)
        scrollToBottom()
      },
      onThinkingDelta: (delta) => {
        if (!deepThink.value) return
        appendAssistant('thinking', delta)
        scrollToBottom()
      },
      onDone: (payload) => {
        const next: Partial<ChatMessage> = { pending: false }
        if (payload.answer) next.content = String(payload.answer)
        if (deepThink.value) {
          if (payload.thinking) next.thinking = String(payload.thinking)
          if (payload.thinking_summary) next.thinkingSummary = String(payload.thinking_summary)
        } else {
          next.thinking = ''
          next.thinkingSummary = ''
        }
        patchAssistant(next)
        const answerText = String(payload.answer || next.content || '')
        applySourcesInsufficientFromAnswer(answerText)
      },
    })
    const latest = messages.value.find((m) => m.id === assistantId)
    if (!latest?.content?.trim()) {
      patchAssistant({ content: '（未返回有效回答）', pending: false })
    } else {
      patchAssistant({ pending: false })
      applySourcesInsufficientFromAnswer(latest.content)
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      patchAssistant({ content: '（已取消）', pending: false })
    } else {
      patchAssistant({
        content: `请求失败：${(err as Error).message || '未知错误'}`,
        pending: false,
      })
      ElMessage.error((err as Error).message || '问答失败')
    }
  } finally {
    sending.value = false
    abortRef.value = null
    await scrollToBottom()
    void refreshHistory()
  }
}

function stop() {
  abortRef.value?.abort()
}

async function copyMessage(msg: ChatMessage) {
  const text = String(msg.content || '').trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    } catch {
      ElMessage.error('复制失败')
      return
    }
  }
  copiedId.value = msg.id
  if (copiedTimer) clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => {
    if (copiedId.value === msg.id) copiedId.value = ''
    copiedTimer = null
  }, 1600)
}

/** Enter 换行；Ctrl/Cmd+Enter 发送 */
function onComposerKeydown(e: Event | KeyboardEvent) {
  const ev = e as KeyboardEvent
  if (ev.key !== 'Enter') return
  if (ev.ctrlKey || ev.metaKey) {
    ev.preventDefault()
    if (canSend.value) void send()
  }
  // 单独 Enter：交给 textarea 插入换行，不提交
}

async function refreshModelOptions() {
  try {
    const data = await listModelConfigs({ is_active: true })
    modelConfigs.value = data.configs || []
  } catch {
    // 未开数据库时模型管理不可用，问答仍可用内置 chat
    modelConfigs.value = []
  }
}

/** 从 KB-20 生效配置同步召回数与匹配度阈值（阈值只读，改在知识库管理） */
async function syncSearchDefaults() {
  try {
    const data = await getKbSettings()
    const settings = data.settings
    const max = Math.max(1, Number(settings.max_search_results) || 20)
    kMax.value = Math.min(100, max)
    const next = Math.max(1, Number(settings.default_k) || 5)
    k.value = Math.min(next, kMax.value)
    const sim = Number(settings.min_source_similarity)
    if (Number.isFinite(sim)) {
      minSimilarity.value = Math.max(0, Math.min(1, sim))
    } else {
      minSimilarity.value = 0.6
    }
  } catch {
    // 配置接口失败时保留当前 k，不打断问答
  }
}

onMounted(() => {
  refreshModelOptions()
  syncSearchDefaults()
  refreshHistory()
})

onBeforeUnmount(() => {
  abortRef.value?.abort()
  if (copiedTimer) clearTimeout(copiedTimer)
})
</script>

<template>
  <div class="qa-layout">
    <aside class="qa-history page-card">
      <div class="qa-history__head">
        <h3>聊天记录</h3>
        <div class="qa-history__actions">
          <el-button
            size="small"
            text
            :icon="Refresh"
            :loading="historyLoading"
            title="刷新"
            @click="refreshHistory"
          />
          <el-button size="small" type="primary" plain @click="newChat">新会话</el-button>
        </div>
      </div>
      <div v-loading="historyLoading" class="qa-history__list">
        <p v-if="!visibleSessions.length && !historyLoading" class="qa-history__empty">暂无历史会话</p>
        <div
          v-for="session in visibleSessions"
          :key="session.session_id"
          class="qa-history__item"
          :class="{ 'is-active': session.session_id === sessionId, 'is-disabled': sending }"
          role="button"
          tabindex="0"
          @click="!sending && openSession(session)"
          @keydown.enter="!sending && openSession(session)"
        >
          <div class="qa-history__title">{{ sessionTitle(session) }}</div>
          <div class="qa-history__meta">
            <span>{{ formatSessionTime(session.timestamp) }}</span>
            <span v-if="session.count">{{ session.count }} 条</span>
          </div>
          <button
            type="button"
            class="qa-history__del"
            title="删除会话"
            aria-label="删除会话"
            @click="removeSession(session, $event)"
          >
            <el-icon :size="14"><Delete /></el-icon>
          </button>
        </div>
      </div>
    </aside>

    <section class="qa-main page-card">
      <div class="qa-toolbar">
        <div class="qa-toolbar__left">
          <el-input
            v-model="userId"
            style="width: 160px"
            placeholder="用户 ID"
            size="small"
            @change="refreshHistory"
          />
          <el-select
            v-model="modelConfigId"
            clearable
            placeholder="默认模型配置"
            size="small"
            style="width: 200px"
            :disabled="sending"
          >
            <el-option label="使用默认模型配置" value="" />
            <el-option
              v-for="cfg in modelConfigs"
              :key="cfg.id"
              :label="`${cfg.name}${cfg.is_default ? ' [默认]' : ''}`"
              :value="String(cfg.id)"
            />
          </el-select>
          <el-input-number
            v-model="k"
            :min="1"
            :max="kMax"
            size="small"
            controls-position="right"
            title="召回数（默认取自「知识库管理 → 检索与分片」）"
          />
          <el-checkbox v-model="deepThink" :disabled="sending">深度思考</el-checkbox>
        </div>
        <div>
          <el-button v-if="sending" size="small" type="danger" plain @click="stop">停止</el-button>
        </div>
      </div>

      <div ref="listRef" class="qa-messages">
        <div v-if="!messages.length" class="qa-empty">输入问题开始检索问答。深度思考默认关闭。</div>
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="qa-msg"
          :class="msg.role"
        >
          <div class="qa-msg__role">{{ msg.role === 'user' ? '我' : '助手' }}</div>
          <div class="qa-msg__col">
            <div class="qa-msg__body">
              <details
                v-if="msg.thinking || msg.thinkingSummary"
                class="qa-think"
                :open="Boolean(msg.pending && msg.thinking)"
              >
                <summary>思考过程</summary>
                <div v-if="msg.thinkingSummary" class="qa-think__summary">{{ msg.thinkingSummary }}</div>
                <pre>{{ msg.thinking }}</pre>
              </details>
              <div class="qa-msg__content">
                <span v-if="msg.pending && !String(msg.content || '').trim()" class="qa-pending">正在生成…</span>
                <pre v-else>{{ msg.content }}</pre>
              </div>
              <div v-if="msg.sources?.length" class="qa-msg__refs">
                {{ isInsufficientAnswer(msg.content) ? '检索候选' : '引用' }}
                {{ msg.sources.length }} 条
                <span v-if="isInsufficientAnswer(msg.content)" class="qa-msg__refs-note">
                  （不足以回答）
                </span>
              </div>
            </div>
            <div
              v-if="!msg.pending && String(msg.content || '').trim()"
              class="qa-msg__toolbar"
            >
              <button
                type="button"
                class="qa-msg__copy"
                :class="{ 'is-copied': copiedId === msg.id }"
                :title="copiedId === msg.id ? '已复制' : '复制'"
                :aria-label="copiedId === msg.id ? '已复制' : '复制'"
                @click="copyMessage(msg)"
              >
                <el-icon :size="14">
                  <Select v-if="copiedId === msg.id" />
                  <CopyDocument v-else />
                </el-icon>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="qa-composer" @keydown="onComposerKeydown">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="输入您的问题…（Enter 换行，Ctrl+Enter 发送）"
          :disabled="sending"
        />
        <el-button type="primary" native-type="button" :loading="sending" :disabled="!canSend" @click="send">
          发送
        </el-button>
      </div>
    </section>

    <aside class="qa-side page-card" :class="{ 'is-insufficient': sourcesInsufficient }">
      <h3>知识来源</h3>
      <p class="source-filter__hint">
        候选过滤线 {{ minSimilarity.toFixed(2) }}（在「知识库管理 → 检索与分片」设置，已存数据库）
      </p>
      <p class="source-filter__hint source-filter__hint--muted">
        这里只列出通过证据判定的来源；没有可靠依据时会直接回答「根据当前知识库无法确定」。下方数字是内部排序分，不是正确率。
      </p>
      <el-alert
        v-if="sourcesInsufficient && sources.length"
        type="warning"
        :closable="false"
        show-icon
        class="source-alert"
        title="模型判断证据不足，以下仅是检索候选，不是已证实依据"
      />
      <p v-if="!sources.length" class="muted">检索命中后将显示于此。</p>
      <template v-else>
        <button
          v-if="sourcesInsufficient"
          type="button"
          class="source-toggle"
          @click="sourcesExpanded = !sourcesExpanded"
        >
          {{ sourcesExpanded ? '收起候选' : `展开 ${sources.length} 条候选` }}
        </button>
        <div v-show="sourcesExpanded || !sourcesInsufficient">
          <div
            v-for="(item, idx) in sources"
            :key="`${item.filename}-${idx}`"
            class="source-item"
          >
            <div class="source-item__title">
              <span>{{ item.filename || '未知文件' }}</span>
              <el-tag size="small" effect="plain" :type="sourceTagType(item)">
                {{ sourceScoreText(item) }}
              </el-tag>
            </div>
            <p v-if="sourceScoreDetail(item)" class="source-item__scores">
              {{ sourceScoreDetail(item) }}
            </p>
            <p>{{ item.preview_text || item.text || '' }}</p>
          </div>
        </div>
      </template>
    </aside>
  </div>
</template>

<style scoped>
.qa-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 300px;
  gap: 16px;
  flex: 1;
  min-height: 0;
  height: 100%;
  max-height: 100%;
  overflow: hidden;
}
.qa-history {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  padding: 0;
  overflow: hidden;
}
.qa-history__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 12px 10px;
  border-bottom: 1px solid var(--color-border);
}
.qa-history__head h3 {
  margin: 0;
  font-size: 15px;
}
.qa-history__actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.qa-history__list {
  flex: 1;
  overflow: auto;
  padding: 8px;
}
.qa-history__empty {
  margin: 24px 8px;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-tertiary);
}
.qa-history__item {
  position: relative;
  width: 100%;
  text-align: left;
  padding: 10px 32px 10px 10px;
  margin-bottom: 6px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.qa-history__item:hover {
  background: var(--color-bg-subtle);
}
.qa-history__item.is-active {
  background: var(--color-primary-subtle);
  border-color: var(--color-border);
}
.qa-history__item.is-disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.qa-history__title {
  font-size: 13px;
  line-height: 1.4;
  color: var(--color-text-primary);
  word-break: break-word;
}
.qa-history__meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.qa-history__del {
  position: absolute;
  top: 8px;
  right: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
}
.qa-history__item:hover .qa-history__del,
.qa-history__del:focus-visible {
  opacity: 1;
}
.qa-history__del:hover {
  background: var(--color-fill-secondary, #f1f5f9);
  color: var(--color-danger, #dc2626);
}
@media (hover: none) {
  .qa-history__del {
    opacity: 1;
  }
}
.qa-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  padding: 0;
  overflow: hidden;
}
.qa-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.qa-toolbar__left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.qa-messages {
  flex: 1;
  overflow: auto;
  padding: 16px;
  background: var(--color-bg-subtle);
}
.qa-empty {
  color: var(--color-text-secondary);
  text-align: center;
  margin-top: 20vh;
}
.qa-msg {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}
.qa-msg.user {
  flex-direction: row-reverse;
}
.qa-msg__role {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-primary-subtle);
  color: var(--color-link);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}
.qa-msg.user .qa-msg__role {
  background: var(--color-primary);
  color: #fff;
}
.qa-msg__col {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  max-width: min(720px, 85%);
  min-width: 0;
}
.qa-msg.user .qa-msg__col {
  align-items: flex-end;
}
.qa-msg__body {
  width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 10px 12px;
}
.qa-msg.user .qa-msg__body {
  background: var(--color-primary-subtle);
}
.qa-msg__content pre,
.qa-think pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.6;
}
.qa-think {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.qa-think__summary {
  margin: 6px 0;
  color: var(--color-text-primary);
}
.qa-pending {
  color: var(--color-text-tertiary);
}
.qa-msg__refs {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-link);
}
.qa-msg__toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  min-height: 28px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.qa-msg:hover .qa-msg__toolbar,
.qa-msg__toolbar:focus-within {
  opacity: 1;
}
.qa-msg__copy {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
}
.qa-msg__copy:hover {
  background: var(--color-fill-secondary, #f1f5f9);
  color: var(--color-text-primary);
}
.qa-msg__copy.is-copied {
  color: var(--color-success, #16a34a);
}
@media (hover: none) {
  .qa-msg__toolbar {
    opacity: 1;
  }
}
.qa-composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
  align-items: end;
  flex-shrink: 0;
  background: var(--color-surface);
  position: relative;
  z-index: 2;
}
.qa-side {
  min-height: 0;
  height: 100%;
  overflow: auto;
}
.qa-side h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
}
.source-filter__hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.45;
}
.source-filter__hint--muted {
  color: var(--color-text-tertiary);
}
.source-alert {
  margin-bottom: 10px;
}
.source-toggle {
  display: block;
  width: 100%;
  margin: 0 0 8px;
  padding: 6px 8px;
  border: 1px dashed var(--color-border);
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.source-toggle:hover {
  color: var(--color-text-primary);
  border-color: var(--color-text-tertiary);
}
.qa-side.is-insufficient .source-item {
  opacity: 0.78;
}
.source-item {
  border-top: 1px solid var(--color-border);
  padding: 10px 0;
}
.source-item__title {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
}
.source-item__scores {
  margin: 0 0 6px !important;
  font-size: 11px !important;
  color: var(--color-text-tertiary) !important;
  -webkit-line-clamp: 2 !important;
}
.source-item p {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.qa-msg__refs-note {
  margin-left: 4px;
  color: var(--color-text-tertiary);
  font-weight: 400;
}
@media (max-width: 1100px) {
  .qa-layout {
    grid-template-columns: 220px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) minmax(140px, 30%);
  }
  .qa-side {
    grid-column: 1 / -1;
    height: auto;
    max-height: 100%;
  }
}
@media (max-width: 720px) {
  .qa-layout {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(120px, 22%) minmax(0, 1fr) minmax(120px, 26%);
  }
  .qa-history {
    max-height: none;
    height: auto;
  }
}
</style>
