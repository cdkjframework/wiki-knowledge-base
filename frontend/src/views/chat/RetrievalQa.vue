<script setup lang="ts">
/**
 * 检索问答：SSE 流式回答、深度思考开关（默认关）、引用来源。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createSession, streamQuery, type SourceResult } from '@/api/query'
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
const k = ref(2)
const deepThink = ref(false)
/** 空字符串表示走默认模型配置 */
const modelConfigId = ref<string>('')
const modelConfigs = ref<ModelConfig[]>([])
const sending = ref(false)
const sources = ref<SourceResult[]>([])
const abortRef = ref<AbortController | null>(null)

const listRef = ref<HTMLElement | null>(null)

const canSend = computed(() => input.value.trim().length > 0 && userId.value.trim().length > 0 && !sending.value)

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
  sessionId.value = ''
  saveSessionId('')
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
        const refs = payload.results || []
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
      },
    })
    const latest = messages.value.find((m) => m.id === assistantId)
    if (!latest?.content?.trim()) {
      patchAssistant({ content: '（未返回有效回答）', pending: false })
    } else {
      patchAssistant({ pending: false })
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
  }
}

function stop() {
  abortRef.value?.abort()
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

onMounted(() => {
  refreshModelOptions()
})

onBeforeUnmount(() => abortRef.value?.abort())
</script>

<template>
  <div class="qa-layout">
    <section class="qa-main page-card">
      <div class="qa-toolbar">
        <div class="qa-toolbar__left">
          <el-input v-model="userId" style="width: 160px" placeholder="用户 ID" size="small" />
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
          <el-input-number v-model="k" :min="1" :max="20" size="small" controls-position="right" />
          <el-checkbox v-model="deepThink" :disabled="sending">深度思考</el-checkbox>
        </div>
        <div>
          <el-button size="small" @click="newChat">新会话</el-button>
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
          <div class="qa-msg__body">
            <details
              v-if="deepThink && (msg.thinking || msg.thinkingSummary)"
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
              引用 {{ msg.sources.length }} 条
            </div>
          </div>
        </div>
      </div>

      <form class="qa-composer" @submit.prevent="send">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="输入您的问题…（Enter 发送需点按钮）"
          :disabled="sending"
        />
        <el-button type="primary" :loading="sending" :disabled="!canSend" @click="send">发送</el-button>
      </form>
    </section>

    <aside class="qa-side page-card">
      <h3>知识来源</h3>
      <p v-if="!sources.length" class="muted">检索命中后将显示于此。</p>
      <div v-for="(item, idx) in sources" :key="`${item.filename}-${idx}`" class="source-item">
        <div class="source-item__title">
          <span>{{ item.filename || '未知文件' }}</span>
          <el-tag size="small" effect="plain">
            {{ typeof item.similarity === 'number' ? item.similarity.toFixed(3) : '-' }}
          </el-tag>
        </div>
        <p>{{ item.preview_text || item.text || '' }}</p>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.qa-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  min-height: calc(100vh - 120px);
}
.qa-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
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
.qa-msg__body {
  max-width: min(720px, 85%);
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
.qa-composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
  align-items: end;
}
.qa-side h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
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
  margin-bottom: 6px;
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
@media (max-width: 960px) {
  .qa-layout {
    grid-template-columns: 1fr;
  }
}
</style>
