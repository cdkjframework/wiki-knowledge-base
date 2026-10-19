<script setup lang="ts">
/**
 * 模型管理：总览 KPI + 分类 Tab + 列表（筛选/分页）/ 增删改 / 设默认 / 测试 / 初始化预设。
 * 无页内子侧栏；分类靠顶部 Tab。知识库分析 = model_type=chat。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  bootstrapModelConfigs,
  createModelConfig,
  deleteModelConfig,
  listLocalHfModels,
  listModelConfigs,
  listModelProviders,
  listRemoteModels,
  setDefaultModelConfig,
  testModelConfig,
  updateModelConfig,
  type LocalHfModel,
  type ModelConfig,
  type ModelConfigPayload,
  type ModelProvider,
  type RetrievalBackend,
} from '@/api/model'
import { getStats } from '@/api/stats'
import ProviderLogo from './ProviderLogo.vue'
import ProviderLogoGrid from './ProviderLogoGrid.vue'
import {
  getProviderBrand,
  brandsForKind,
  buildQwenCnBaseUrl,
  isQwenCnProvider,
  isQwenCnWorkspaceUrlReady,
  parseQwenCnEndpoint,
  type ProviderBrand,
  type QwenCnEndpointMode,
} from './providerCatalog'

type ModelKind = 'embedding' | 'rerank' | 'chat'

const KIND_META: Record<
  ModelKind,
  { label: string; desc: string; kpi: string; accent: string }
> = {
  embedding: {
    label: 'Embedding 模型',
    desc: '用于文本向量化',
    kpi: '用于文本向量化',
    accent: 'purple',
  },
  rerank: {
    label: 'Reranker 模型',
    desc: '用于检索结果重排序',
    kpi: '用于检索结果重排序',
    accent: 'green',
  },
  chat: {
    label: '知识库分析模型',
    desc: '用于问答、摘要、分析等',
    kpi: '用于问答、摘要、分析等',
    accent: 'amber',
  },
}

const loading = ref(false)
const rows = ref<ModelConfig[]>([])
const providers = ref<ModelProvider[]>([])
const localModels = ref<LocalHfModel[]>([])
/** API 服务商拉取到的远程模型列表 */
const remoteModels = ref<Array<{ id: string; label?: string }>>([])
const fetchingModels = ref(false)
/** embedding/rerank：本地 HF 或 API */
const loadMode = ref<'local' | 'api'>('local')
const runtime = ref<{
  embedding_model?: string
  reranker_model?: string
  chat_model?: string
  embedding_backend?: string
  reranker_backend?: string
  chat_backend?: string
  dimension?: number | null
  device_label?: string
}>({})

function backendLabel(backend?: string | null): string {
  const b = String(backend || '').trim().toLowerCase()
  if (b === 'local_hf' || b === 'local' || b === 'huggingface') return '本地 HuggingFace'
  if (b === 'openai_compat' || b === 'api' || b === 'remote') return 'API 接口'
  return backend ? String(backend) : '—'
}

function formatRuntimeSwitch(runtime?: {
  model?: string
  backend?: RetrievalBackend | string
  warnings?: string[]
} | null): string {
  if (!runtime?.model) return ''
  return `${runtime.model}（${backendLabel(runtime.backend)}）`
}

const activeKind = ref<ModelKind>('embedding')
const headerQuery = ref('')
const tableQuery = ref('')
const statusFilter = ref<'all' | 'active' | 'inactive'>('all')
const page = ref(1)
const pageSize = ref(10)

const dialogVisible = ref(false)
const dialogTitle = ref('新增模型')
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  provider: '',
  base_url: '',
  model_name: '',
  model_type: 'chat' as ModelKind,
  api_key: '',
  temperature: 0.7,
  max_tokens: undefined as number | undefined,
  dimension: undefined as number | undefined,
  max_input_length: undefined as number | undefined,
  timeout: 30,
  description: '',
  is_active: true,
  is_default: false,
})

/** 通义国内：普通共享 vs 业务空间/Team */
const qwenCnMode = ref<QwenCnEndpointMode>('shared')
const qwenWorkspaceId = ref('')
const isQwenCn = computed(() => isQwenCnProvider(form.provider))

function syncQwenCnBaseUrl() {
  if (!isQwenCn.value) return
  form.base_url = buildQwenCnBaseUrl(qwenCnMode.value, qwenWorkspaceId.value)
}

const qwenCnModeModel = computed({
  get: () => qwenCnMode.value,
  set: (v: QwenCnEndpointMode) => {
    qwenCnMode.value = v === 'workspace' ? 'workspace' : 'shared'
    syncQwenCnBaseUrl()
  },
})

watch(qwenWorkspaceId, () => {
  if (isQwenCn.value && qwenCnMode.value === 'workspace') syncQwenCnBaseUrl()
})

function normalizeKind(raw: string | undefined | null): ModelKind {
  const t = String(raw || 'chat').trim().toLowerCase()
  if (t === 'embedding' || t === 'embed') return 'embedding'
  if (t === 'rerank' || t === 'reranker') return 'rerank'
  return 'chat'
}

const BUILTIN_PROVIDERS: ModelProvider[] = [
  {
    name: 'huggingface',
    base_url: 'local://huggingface',
    requires_api_key: false,
    local_load: true,
    model_types: ['embedding', 'rerank'],
    label: 'HuggingFace 本地加载',
  },
  { name: 'ollama', base_url: 'http://127.0.0.1:11434/v1', requires_api_key: false, model_types: ['chat'] },
  {
    name: 'lm_studio',
    base_url: 'http://127.0.0.1:1234/v1',
    requires_api_key: false,
    model_types: ['chat', 'embedding', 'rerank'],
  },
]

function mergeProviders(fromApi: ModelProvider[]): ModelProvider[] {
  const map = new Map<string, ModelProvider>()
  for (const p of BUILTIN_PROVIDERS) map.set(p.name, { ...p })
  for (const p of fromApi || []) {
    if (!p?.name) continue
    map.set(p.name, { ...map.get(p.name), ...p })
  }
  const preferred = ['huggingface', 'ollama', 'lm_studio']
  const rest = [...map.keys()].filter((k) => !preferred.includes(k)).sort()
  return [...preferred, ...rest].map((k) => map.get(k)!).filter(Boolean)
}

function isLocalHfProvider(name: string): boolean {
  const n = (name || '').trim().toLowerCase()
  return n === 'huggingface' || n === 'hf' || n === 'local_hf' || n === 'local'
}

const selectedProvider = computed(() => providers.value.find((p) => p.name === form.provider))
const isLocalHf = computed(() => isLocalHfProvider(form.provider))
const apiKeyPlaceholder = computed(() => {
  if (editingId.value) return '留空表示不修改'
  if (selectedProvider.value?.requires_api_key === false || isLocalHf.value) return '本地服务可留空'
  return '可留空'
})

const providersForForm = computed(() => {
  const kind = form.model_type
  return providers.value.filter((p) => {
    const types = p.model_types
    if (!types || !types.length) {
      // API 未带 model_types 时，按品牌目录判定
      const brand = getProviderBrand(p.name)
      return brand.modelTypes.includes(kind)
    }
    return types.includes(kind)
  })
})

/** Logo 宫格可用 id：Embedding/Rerank 不含纯聊天商；API 模式再去掉 huggingface */
const providersForKindIds = computed(() => {
  const kind = form.model_type
  const ids = brandsForKind(kind).map((b) => b.id)
  if (kind === 'embedding' || kind === 'rerank') {
    if (loadMode.value === 'api') {
      return ids.filter((id) => id !== 'huggingface')
    }
  }
  return ids
})

const counts = computed(() => {
  const c = { total: rows.value.length, embedding: 0, rerank: 0, chat: 0 }
  for (const row of rows.value) {
    c[normalizeKind(row.model_type)] += 1
  }
  return c
})

const kindFiltered = computed(() => {
  let list = rows.value.filter((r) => normalizeKind(r.model_type) === activeKind.value)
  const q = (tableQuery.value || headerQuery.value).trim().toLowerCase()
  if (q) {
    list = list.filter((r) => {
      const blob = `${r.name} ${r.provider} ${r.model_name} ${r.description || ''}`.toLowerCase()
      return blob.includes(q)
    })
  }
  if (statusFilter.value === 'active') list = list.filter((r) => r.is_active)
  if (statusFilter.value === 'inactive') list = list.filter((r) => !r.is_active)
  return list
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return kindFiltered.value.slice(start, start + pageSize.value)
})

watch([activeKind, tableQuery, headerQuery, statusFilter, pageSize], () => {
  page.value = 1
})

function pickDefaultProvider(kind: ModelKind): ModelProvider | undefined {
  if (kind === 'embedding' || kind === 'rerank') {
    const hf = providers.value.find((p) => p.name === 'huggingface')
    if (hf) return hf
    return {
      name: 'huggingface',
      base_url: 'local://huggingface',
      requires_api_key: false,
      local_load: true,
      model_types: ['embedding', 'rerank'],
    }
  }
  const list = providers.value.filter((p) => {
    const types = p.model_types
    if (!types || !types.length) return true
    return types.includes(kind)
  })
  return list.find((p) => p.name === 'ollama' || p.name === 'lm_studio') || list[0]
}

function applyLoadMode(mode: 'local' | 'api') {
  const prev = loadMode.value
  loadMode.value = mode
  if (form.model_type !== 'embedding' && form.model_type !== 'rerank') return
  if (mode === 'local') {
    form.provider = 'huggingface'
    form.base_url = 'local://huggingface'
    remoteModels.value = []
    // 切到本地：丢掉 API 残留，默认选白名单第一项（仅本地框）
    const ids = new Set(localModels.value.map((m) => m.id))
    if (prev !== 'local' || !form.model_name || !ids.has(form.model_name)) {
      form.model_name = localModels.value[0]?.id || ''
    }
  } else {
    if (isLocalHfProvider(form.provider)) {
      const hit = providers.value.find((p) => p.name === 'openai' || p.name === 'lm_studio' || p.name === 'qwen')
      form.provider = hit?.name || 'qwen'
      onProviderChange(form.provider)
    }
    // 切到 API：不要把 HF 路径留在「模型标识」里
    const ids = new Set(localModels.value.map((m) => m.id))
    if (prev === 'local' || ids.has(form.model_name) || /^Qwen\//i.test(form.model_name)) {
      form.model_name = ''
    }
    remoteModels.value = []
  }
}

function onLoadModeUpdate(v: string | number | boolean) {
  applyLoadMode(String(v) === 'api' ? 'api' : 'local')
}

function resetForm() {
  editingId.value = null
  form.name = ''
  form.model_type = activeKind.value
  form.api_key = ''
  form.temperature = 0.7
  form.max_tokens = undefined
  form.dimension = undefined
  form.max_input_length = undefined
  form.timeout = 30
  form.description = ''
  form.is_active = true
  form.is_default = false
  form.model_name = ''
  remoteModels.value = []
  qwenCnMode.value = 'shared'
  qwenWorkspaceId.value = ''
  if (activeKind.value === 'embedding' || activeKind.value === 'rerank') {
    loadMode.value = 'local'
    form.provider = 'huggingface'
    form.base_url = 'local://huggingface'
  } else {
    loadMode.value = 'api'
    const hit = pickDefaultProvider(activeKind.value)
    form.provider = hit?.name || ''
    form.base_url = hit?.base_url || ''
    if (isQwenCnProvider(form.provider)) syncQwenCnBaseUrl()
  }
}

function onProviderChange(name: string) {
  remoteModels.value = []
  const hit = providers.value.find((p) => p.name === name)
  const brand = getProviderBrand(name)
  if (isQwenCnProvider(name)) {
    // 通义默认国内普通接口；若当前已是 team 域名则保留解析结果
    const parsed = parseQwenCnEndpoint(form.base_url)
    if (parsed.mode === 'workspace' && parsed.workspaceId) {
      qwenCnMode.value = 'workspace'
      qwenWorkspaceId.value = parsed.workspaceId
    } else {
      qwenCnMode.value = 'shared'
      qwenWorkspaceId.value = ''
    }
    syncQwenCnBaseUrl()
  } else {
    const url = hit?.base_url || brand.defaultBaseUrl || ''
    if (url && !editingId.value) {
      form.base_url = url
    } else if (url && !form.base_url.trim()) {
      form.base_url = url
    }
  }
  if (isLocalHfProvider(name)) loadMode.value = 'local'
  else if (form.model_type === 'embedding' || form.model_type === 'rerank') loadMode.value = 'api'
}

function onPickProviderBrand(b: ProviderBrand) {
  form.provider = b.id
  onProviderChange(b.id)
}

function onPickLocalModel(id: string) {
  form.model_name = id
  if (!form.name.trim()) {
    const hit = localModels.value.find((m) => m.id === id)
    form.name = hit?.label || id.split('/').pop() || id
  }
}

async function onFetchRemoteModels() {
  if (isLocalHf.value) return
  const provider = form.provider.trim()
  const baseUrl = form.base_url.trim()
  if (!provider) {
    ElMessage.warning('请先选择服务商')
    return
  }
  if (!baseUrl) {
    ElMessage.warning('请先填写接口地址')
    return
  }
  fetchingModels.value = true
  try {
    const data = await listRemoteModels({
      provider,
      base_url: baseUrl,
      api_key: form.api_key.trim() || undefined,
      timeout: Number(form.timeout) || 30,
      config_id: editingId.value ?? undefined,
    })
    if (!data.ok) {
      remoteModels.value = []
      ElMessage.error(data.error || '获取模型失败')
      return
    }
    remoteModels.value = data.models || []
    if (!remoteModels.value.length) {
      ElMessage.warning('上游未返回可用模型')
      return
    }
    const ids = new Set(remoteModels.value.map((m) => m.id))
    if (form.model_name && !ids.has(form.model_name)) {
      // 保留手填值：下拉里加一项
      remoteModels.value = [{ id: form.model_name, label: form.model_name }, ...remoteModels.value]
    } else if (!form.model_name) {
      form.model_name = remoteModels.value[0].id
    }
    ElMessage.success(`已获取 ${data.count ?? remoteModels.value.length} 个模型`)
  } catch (err) {
    remoteModels.value = []
    ElMessage.error((err as Error).message || '获取模型失败')
  } finally {
    fetchingModels.value = false
  }
}

watch(
  () => form.model_type,
  async (kind) => {
    if (kind === 'embedding' || kind === 'rerank') {
      await refreshLocalModels(kind)
      if (loadMode.value === 'local' || isLocalHfProvider(form.provider)) {
        applyLoadMode('local')
      }
    } else {
      loadMode.value = 'api'
      const ok = providersForForm.value.some((p) => p.name === form.provider)
      if (!ok || isLocalHfProvider(form.provider)) {
        const hit = pickDefaultProvider(kind)
        form.provider = hit?.name || ''
        form.base_url = hit?.base_url || ''
      }
    }
  },
)

async function refreshProviders() {
  try {
    const data = await listModelProviders()
    providers.value = mergeProviders(data.providers || [])
  } catch (err) {
    providers.value = mergeProviders([])
    ElMessage.error((err as Error).message || '加载服务商失败（需启用数据库后端）')
  }
}

async function refreshLocalModels(kind?: ModelKind) {
  const k = kind || form.model_type
  if (k !== 'embedding' && k !== 'rerank') {
    localModels.value = []
    return
  }
  try {
    const data = await listLocalHfModels(k)
    localModels.value = data.models || []
  } catch {
    // 后端未重启时兜底：仅 Qwen3 Embedding / Reranker 固定版本
    localModels.value =
      k === 'embedding'
        ? [
            { id: 'Qwen/Qwen3-Embedding-0.6B', label: 'Qwen3-Embedding-0.6B', recommended: true },
            { id: 'Qwen/Qwen3-Embedding-4B', label: 'Qwen3-Embedding-4B', recommended: true },
            { id: 'Qwen/Qwen3-Embedding-8B', label: 'Qwen3-Embedding-8B', recommended: true },
          ]
        : [
            { id: 'Qwen/Qwen3-Reranker-0.6B', label: 'Qwen3-Reranker-0.6B', recommended: true },
            { id: 'Qwen/Qwen3-Reranker-4B', label: 'Qwen3-Reranker-4B', recommended: true },
            { id: 'Qwen/Qwen3-Reranker-8B', label: 'Qwen3-Reranker-8B', recommended: true },
          ]
  }
}

async function refreshRuntime() {
  try {
    const data = await getStats()
    const s = (data.stats || {}) as Record<string, unknown>
    runtime.value = {
      embedding_model: String(s.embedding_model || ''),
      reranker_model: String(s.reranker_model || ''),
      chat_model: String(s.chat_model || ''),
      embedding_backend: String(s.embedding_backend || ''),
      reranker_backend: String(s.reranker_backend || ''),
      chat_backend: String(s.chat_backend || ''),
      dimension: (s.dimension as number | null | undefined) ?? null,
      device_label: String(s.device || s.device_label || ''),
    }
  } catch {
    runtime.value = {}
  }
}

async function refreshConfigs() {
  loading.value = true
  try {
    const data = await listModelConfigs()
    rows.value = data.configs || []
  } catch (err) {
    ElMessage.error((err as Error).message || '加载模型配置失败')
  } finally {
    loading.value = false
  }
}

function displayMaxInput(row: ModelConfig): string {
  if (row.max_input_length != null && row.max_input_length > 0) return String(row.max_input_length)
  if (row.max_tokens != null && row.max_tokens > 0) return String(row.max_tokens)
  return '—'
}

function displayDimension(row: ModelConfig): string {
  if (row.dimension != null && row.dimension > 0) return String(row.dimension)
  return '—'
}

async function openCreate() {
  resetForm()
  dialogTitle.value = '新增模型'
  if (form.model_type === 'embedding' || form.model_type === 'rerank') {
    await refreshLocalModels(form.model_type)
    applyLoadMode('local')
  }
  dialogVisible.value = true
}

async function openEdit(row: ModelConfig) {
  editingId.value = row.id
  dialogTitle.value = '编辑模型'
  remoteModels.value = []
  form.name = row.name || ''
  form.provider = row.provider || ''
  form.base_url = row.base_url || ''
  form.model_name = row.model_name || ''
  form.model_type = normalizeKind(row.model_type)
  form.api_key = ''
  form.temperature = row.temperature ?? 0.7
  form.max_tokens = row.max_tokens ?? undefined
  form.dimension = row.dimension ?? undefined
  form.max_input_length = row.max_input_length ?? undefined
  form.timeout = row.timeout ?? 30
  form.description = row.description || ''
  form.is_active = Boolean(row.is_active)
  form.is_default = Boolean(row.is_default)
  if (isQwenCnProvider(form.provider)) {
    const parsed = parseQwenCnEndpoint(form.base_url)
    qwenCnMode.value = parsed.mode
    qwenWorkspaceId.value = parsed.workspaceId
  } else {
    qwenCnMode.value = 'shared'
    qwenWorkspaceId.value = ''
  }
  if (form.model_type === 'embedding' || form.model_type === 'rerank') {
    await refreshLocalModels(form.model_type)
    loadMode.value = isLocalHfProvider(form.provider) ? 'local' : 'api'
  } else {
    loadMode.value = 'api'
  }
  dialogVisible.value = true
}

function buildPayload(): ModelConfigPayload {
  const provider = form.provider.trim()
  const body: ModelConfigPayload = {
    name: form.name.trim(),
    provider,
    base_url: isLocalHfProvider(provider)
      ? form.base_url.trim() || 'local://huggingface'
      : form.base_url.trim(),
    model_name: form.model_name.trim(),
    model_type: form.model_type,
    temperature: Number(form.temperature),
    timeout: Number(form.timeout),
    is_active: form.is_active,
    is_default: form.is_default,
    description: form.description.trim() || null,
  }
  if (form.api_key.trim()) body.api_key = form.api_key.trim()
  if (form.max_tokens != null && Number(form.max_tokens) > 0) {
    body.max_tokens = Number(form.max_tokens)
  } else {
    body.max_tokens = null
  }
  if (form.dimension != null && Number(form.dimension) > 0) {
    body.dimension = Number(form.dimension)
  } else {
    body.dimension = null
  }
  if (form.max_input_length != null && Number(form.max_input_length) > 0) {
    body.max_input_length = Number(form.max_input_length)
  } else {
    body.max_input_length = null
  }
  return body
}

async function onSave() {
  const body = buildPayload()
  if (!body.name || !body.provider || !body.model_name) {
    ElMessage.warning('名称、服务商、模型标识不能为空')
    return
  }
  if (!isLocalHfProvider(body.provider) && !body.base_url) {
    ElMessage.warning('接口地址不能为空')
    return
  }
  if (isQwenCnProvider(body.provider) && qwenCnMode.value === 'workspace') {
    if (!qwenWorkspaceId.value.trim() || !isQwenCnWorkspaceUrlReady(body.base_url)) {
      ElMessage.warning('Team / 业务空间请填写 WorkspaceId')
      return
    }
  }
  saving.value = true
  try {
    const saveResult =
      editingId.value != null
        ? await updateModelConfig(editingId.value, body)
        : await createModelConfig(body)
    const runtimeInfo = (saveResult as { runtime?: { model?: string; backend?: string; warnings?: string[] } })
      .runtime
    if (runtimeInfo?.warnings?.length) {
      ElMessage.warning(runtimeInfo.warnings.join('；'))
    }
    const switched = formatRuntimeSwitch(runtimeInfo)
    if (editingId.value != null) {
      ElMessage.success(switched ? `模型配置已更新，运行时已切换为 ${switched}` : '模型配置已更新')
    } else {
      ElMessage.success(switched ? `模型配置已新增，运行时已切换为 ${switched}` : '模型配置已新增')
      activeKind.value = normalizeKind(body.model_type)
    }
    dialogVisible.value = false
    await refreshConfigs()
    if (
      runtimeInfo ||
      body.is_default
    ) {
      await refreshRuntime()
    }
  } catch (err) {
    ElMessage.error((err as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(row: ModelConfig) {
  try {
    await ElMessageBox.confirm(`确定删除模型配置「${row.name}」？`, '删除确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteModelConfig(row.id)
    ElMessage.success('已删除')
    await refreshConfigs()
  } catch (err) {
    ElMessage.error((err as Error).message || '删除失败')
  }
}

async function onSetDefault(row: ModelConfig) {
  try {
    const data = await setDefaultModelConfig(row.id)
    const runtimeInfo = data.runtime
    if (runtimeInfo?.warnings?.length) {
      ElMessage.warning(runtimeInfo.warnings.join('；'))
    }
    const switched = formatRuntimeSwitch(runtimeInfo)
    ElMessage.success(
      switched
        ? `已将「${row.name}」设为默认，运行时已切换为 ${switched}`
        : `已将「${row.name}」设为默认`,
    )
    await refreshConfigs()
    await refreshRuntime()
  } catch (err) {
    ElMessage.error((err as Error).message || '设置默认失败')
  }
}

async function onTest(row: ModelConfig) {
  try {
    const data = await testModelConfig({ config_id: row.id })
    if (data.ok === false || data.success === false) {
      ElMessage.error(data.error || data.message || '连通性测试失败')
      return
    }
    const latency = data.latency_ms != null ? `（${data.latency_ms} ms）` : ''
    ElMessage.success(data.message || `连通正常${latency}`)
  } catch (err) {
    ElMessage.error((err as Error).message || '连通性测试失败')
  }
}

async function onBootstrap() {
  try {
    await ElMessageBox.confirm('将写入内置预设（已存在的同名配置会跳过），是否继续？', '初始化预设', {
      type: 'info',
    })
  } catch {
    return
  }
  try {
    const data = await bootstrapModelConfigs()
    ElMessage.success(data.message || `初始化完成：新建 ${data.created ?? 0}，跳过 ${data.skipped ?? 0}`)
    await refreshConfigs()
  } catch (err) {
    ElMessage.error((err as Error).message || '初始化失败')
  }
}

onMounted(async () => {
  await refreshProviders()
  await Promise.all([refreshConfigs(), refreshRuntime(), refreshLocalModels(activeKind.value)])
})
</script>

<template>
  <div class="model-page">
    <header class="model-hero">
      <div>
        <h1 class="model-hero__title">模型管理</h1>
        <p class="model-hero__desc">统一管理 Embedding、Reranker 和知识库分析模型，灵活配置、高效运行。</p>
        <p class="model-hero__note">
          Embedding / Reranker / 知识库分析 均由<strong>默认配置</strong>决定运行后端；
          「设为默认」或保存当前默认配置后立即热切换，无需重启。
          维度与向量库不一致时不会自动改索引。点「初始化预设」可写入本地 HF 示例（同名跳过）。
        </p>
      </div>
      <div class="model-hero__actions">
        <el-input
          v-model="headerQuery"
          clearable
          class="model-hero__search"
          placeholder="搜索模型名称 / 服务商 / 标识"
        />
        <el-button @click="onBootstrap">初始化预设</el-button>
        <el-button type="primary" @click="openCreate">+ 新增模型</el-button>
      </div>
    </header>

    <section v-if="runtime.embedding_model || runtime.reranker_model" class="runtime-card page-card">
      <h3 class="runtime-card__title">当前运行时（默认可热切换）</h3>
      <div class="runtime-card__grid">
        <div>
          <span class="runtime-card__label">Embedding</span>
          <code>{{ runtime.embedding_model || '—' }}</code>
          <span class="runtime-card__backend">{{ backendLabel(runtime.embedding_backend) }}</span>
        </div>
        <div>
          <span class="runtime-card__label">Reranker</span>
          <code>{{ runtime.reranker_model || '—' }}</code>
          <span class="runtime-card__backend">{{ backendLabel(runtime.reranker_backend) }}</span>
        </div>
        <div>
          <span class="runtime-card__label">分析 / Chat</span>
          <code>{{ runtime.chat_model || '—' }}</code>
          <span class="runtime-card__backend">{{ backendLabel(runtime.chat_backend) }}</span>
        </div>
        <div>
          <span class="runtime-card__label">向量维度</span>
          <strong>{{ runtime.dimension || '—' }}</strong>
        </div>
        <div>
          <span class="runtime-card__label">推理设备</span>
          <strong>{{ runtime.device_label || '—' }}</strong>
        </div>
      </div>
      <p class="runtime-card__hint">
        Embedding / Reranker / 知识库分析均由默认配置驱动；设为默认或保存默认配置后立即热切换。
      </p>
    </section>

    <section class="kpi-grid">
      <article class="kpi-card">
        <div class="kpi-card__icon kpi-card__icon--blue">◈</div>
        <div>
          <div class="kpi-card__label">模型总数</div>
          <div class="kpi-card__value">{{ counts.total }}</div>
          <div class="kpi-card__hint">已配置的模型总数</div>
        </div>
      </article>
      <article class="kpi-card">
        <div class="kpi-card__icon kpi-card__icon--purple">▣</div>
        <div>
          <div class="kpi-card__label">Embedding 模型</div>
          <div class="kpi-card__value">{{ counts.embedding }}</div>
          <div class="kpi-card__hint">{{ KIND_META.embedding.kpi }}</div>
        </div>
      </article>
      <article class="kpi-card">
        <div class="kpi-card__icon kpi-card__icon--green">▤</div>
        <div>
          <div class="kpi-card__label">Reranker 模型</div>
          <div class="kpi-card__value">{{ counts.rerank }}</div>
          <div class="kpi-card__hint">{{ KIND_META.rerank.kpi }}</div>
        </div>
      </article>
      <article class="kpi-card">
        <div class="kpi-card__icon kpi-card__icon--amber">✦</div>
        <div>
          <div class="kpi-card__label">知识库分析模型</div>
          <div class="kpi-card__value">{{ counts.chat }}</div>
          <div class="kpi-card__hint">{{ KIND_META.chat.kpi }}</div>
        </div>
      </article>
    </section>

    <section class="panel page-card">
      <el-tabs v-model="activeKind" class="model-tabs">
        <el-tab-pane
          :label="`Embedding 模型 (${counts.embedding})`"
          name="embedding"
        />
        <el-tab-pane :label="`Reranker 模型 (${counts.rerank})`" name="rerank" />
        <el-tab-pane :label="`知识库分析模型 (${counts.chat})`" name="chat" />
      </el-tabs>

      <div class="panel-toolbar">
        <div>
          <h3 class="panel-toolbar__title">{{ KIND_META[activeKind].label }}</h3>
          <p class="panel-toolbar__desc">{{ KIND_META[activeKind].desc }}</p>
        </div>
        <div class="panel-toolbar__filters">
          <el-input v-model="tableQuery" clearable placeholder="搜索模型…" style="width: 180px" />
          <el-select v-model="statusFilter" style="width: 120px">
            <el-option label="全部状态" value="all" />
            <el-option label="启用" value="active" />
            <el-option label="停用" value="inactive" />
          </el-select>
          <el-button :loading="loading" @click="refreshConfigs">刷新</el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="pagedRows"
        empty-text="暂无该类模型配置"
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="模型名称" min-width="160">
          <template #default="{ row }">
            <span class="name-cell">
              {{ row.name }}
              <el-tag v-if="row.is_default" size="small" type="warning" effect="plain" class="rec-tag">
                推荐
              </el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="服务商" min-width="160">
          <template #default="{ row }">
            <span class="provider-cell">
              <ProviderLogo
                :provider-id="row.provider"
                size="sm"
                :show-label="false"
              />
              <span>{{ getProviderBrand(row.provider).label }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型标识" min-width="160" show-overflow-tooltip />
        <el-table-column label="维度" width="90">
          <template #default="{ row }">{{ displayDimension(row) }}</template>
        </el-table-column>
        <el-table-column label="最大输入长度" width="120">
          <template #default="{ row }">{{ displayMaxInput(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="status-dot" :class="row.is_active ? 'is-on' : 'is-off'">
              {{ row.is_active ? '启用' : '停用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <span :class="row.is_default ? 'default-yes' : 'default-no'">
              {{ row.is_default ? '是' : '否' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="onTest(row)">测试</el-button>
            <el-button link type="primary" :disabled="row.is_default" @click="onSetDefault(row)">
              设为默认
            </el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="panel-footer">
        <span class="muted">共 {{ kindFiltered.length }} 条</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          background
          layout="prev, pager, next, sizes"
          :total="kindFiltered.length"
          :page-sizes="[10, 20, 50]"
        />
      </div>
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="720px"
      destroy-on-close
      align-center
      class="model-config-dialog"
    >
      <el-form label-width="110px">
        <el-form-item label="模型类型" required>
          <el-radio-group v-model="form.model_type">
            <el-radio-button value="embedding">Embedding</el-radio-button>
            <el-radio-button value="rerank">Reranker</el-radio-button>
            <el-radio-button value="chat">知识库分析</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="form.model_type === 'embedding' || form.model_type === 'rerank'"
          label="加载方式"
          required
        >
          <el-radio-group :model-value="loadMode" @update:model-value="onLoadModeUpdate">
            <el-radio-button value="local">本地 HuggingFace</el-radio-button>
            <el-radio-button value="api">API 服务商</el-radio-button>
          </el-radio-group>
          <div class="field-hint">
            本配置决定检索走本地还是接口；设为默认或保存当前默认配置后立即热切换到运行时。
          </div>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="显示名称" />
        </el-form-item>
        <el-form-item v-if="loadMode === 'api' || form.model_type === 'chat'" label="服务商" required>
          <ProviderLogoGrid
            v-model="form.provider"
            :kind="form.model_type"
            :available-ids="providersForKindIds"
            @select="onPickProviderBrand"
          />
        </el-form-item>
        <el-form-item v-if="isLocalHf" label="本地来源">
          <el-input model-value="进程内 HuggingFace（仅 Qwen3 Embedding / Reranker）" disabled />
        </el-form-item>
        <template v-else-if="isQwenCn && (loadMode === 'api' || form.model_type === 'chat')">
          <el-form-item label="国内接口" required>
            <el-radio-group v-model="qwenCnModeModel">
              <el-radio-button value="shared">普通接口</el-radio-button>
              <el-radio-button value="workspace">Team / 业务空间</el-radio-button>
            </el-radio-group>
            <div class="field-hint">
              普通：dashscope.aliyuncs.com（国内共享）。Team：{WorkspaceId}.cn-beijing.maas.aliyuncs.com。国际请用 dashscope-intl。
            </div>
          </el-form-item>
          <el-form-item v-if="qwenCnMode === 'workspace'" label="WorkspaceId" required>
            <el-input
              v-model="qwenWorkspaceId"
              placeholder="业务空间 ID，如 llm-xxxx"
            />
            <div class="field-hint">填写后自动写入上方接口地址；未填写时地址保留模板以便区分普通接口。</div>
          </el-form-item>
          <el-form-item label="接口地址" required>
            <el-input v-model="form.base_url" placeholder="由上方选项自动生成，可微调" />
          </el-form-item>
        </template>
        <el-form-item
          v-else-if="loadMode === 'api' || form.model_type === 'chat'"
          label="接口地址"
          required
        >
          <el-input v-model="form.base_url" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item v-if="isLocalHf" label="本地模型" required>
          <el-select
            v-model="form.model_name"
            filterable
            style="width: 100%"
            placeholder="选择 Qwen3 本地模型版本"
            @change="onPickLocalModel"
          >
            <el-option
              v-for="m in localModels"
              :key="m.id"
              :label="`${m.label}${m.cached ? '（已缓存）' : ''}`"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="模型标识" required>
          <div class="model-id-row">
            <el-select
              v-if="remoteModels.length"
              v-model="form.model_name"
              filterable
              allow-create
              default-first-option
              clearable
              style="flex: 1; min-width: 0"
              placeholder="从列表选择或手动输入"
            >
              <el-option
                v-for="m in remoteModels"
                :key="m.id"
                :label="m.label || m.id"
                :value="m.id"
              />
            </el-select>
            <el-input
              v-else
              v-model="form.model_name"
              style="flex: 1; min-width: 0"
              :placeholder="form.provider === 'ollama' ? '如 qwen2.5:7b' : '如 text-embedding-3-large'"
            />
            <el-button :loading="fetchingModels" @click="onFetchRemoteModels">获取模型</el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="!isLocalHf" label="API 密钥">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="apiKeyPlaceholder"
          />
        </el-form-item>
        <el-form-item v-if="form.model_type === 'chat'" label="temperature">
          <el-input-number v-model="form.temperature" :step="0.1" :min="0" :max="2" />
        </el-form-item>
        <el-form-item v-if="form.model_type === 'embedding'" label="维度 dimension">
          <el-input-number v-model="form.dimension" :min="1" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="最大输入长度">
          <el-input-number
            v-model="form.max_input_length"
            :min="1"
            :step="1"
            controls-position="right"
            placeholder="如 8192"
          />
        </el-form-item>
        <el-form-item v-if="form.model_type === 'chat'" label="max_tokens">
          <el-input-number v-model="form.max_tokens" :min="1" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="timeout(秒)">
          <el-input-number v-model="form.timeout" :min="1" :step="0.5" :precision="1" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="可选描述" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.model-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: calc(100vh - 120px);
}

.model-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.model-hero__title {
  margin: 0 0 6px;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.model-hero__desc {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 0.95rem;
  max-width: 36rem;
}

.model-hero__note {
  margin: 8px 0 0;
  font-size: 0.8rem;
  color: var(--color-text-tertiary);
  max-width: 40rem;
  line-height: 1.5;
}

.model-hero__note code {
  font-size: 0.78rem;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--color-primary-subtle);
  color: var(--color-primary);
}

.model-hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.model-hero__search {
  width: 260px;
}

.runtime-card__title {
  margin: 0 0 12px;
  font-size: 1rem;
}
.runtime-card__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}
.runtime-card__label {
  display: block;
  font-size: 0.75rem;
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
}
.runtime-card code {
  font-size: 0.8rem;
  word-break: break-all;
}
.runtime-card__backend {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 8px;
  font-size: 0.72rem;
  color: var(--color-text-secondary, #64748b);
  background: var(--color-fill-secondary, #f1f5f9);
  border-radius: 4px;
  vertical-align: middle;
}
.runtime-card__hint {
  margin: 12px 0 0;
  font-size: 0.8rem;
  color: var(--color-text-tertiary);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.kpi-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 18px 20px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.kpi-card__icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  font-size: 18px;
  flex-shrink: 0;
}

.kpi-card__icon--blue {
  background: var(--color-primary-subtle);
  color: var(--color-primary);
}
.kpi-card__icon--purple {
  background: #f3e8ff;
  color: #7c3aed;
}
.kpi-card__icon--green {
  background: #e8f8ef;
  color: var(--color-success);
}
.kpi-card__icon--amber {
  background: #fff7e8;
  color: var(--color-warning);
}

.kpi-card__label {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}
.kpi-card__value {
  margin-top: 4px;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.1;
}
.kpi-card__hint {
  margin-top: 4px;
  font-size: 0.8rem;
  color: var(--color-text-tertiary);
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.model-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
}

.panel-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.panel-toolbar__title {
  margin: 0 0 4px;
  font-size: 1.05rem;
}
.panel-toolbar__desc {
  margin: 0;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}
.panel-toolbar__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.name-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.rec-tag {
  border-radius: 999px;
}

.provider-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.status-dot::before {
  content: '';
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.status-dot.is-on {
  color: var(--color-success);
}
.status-dot.is-on::before {
  background: var(--color-success);
}
.status-dot.is-off {
  color: var(--color-text-tertiary);
}
.status-dot.is-off::before {
  background: var(--color-text-tertiary);
}

.default-yes {
  color: var(--color-warning);
  font-weight: 600;
}
.default-no {
  color: var(--color-text-tertiary);
}

.panel-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding-top: 8px;
}
.muted {
  color: var(--color-text-tertiary);
  font-size: 0.85rem;
}

.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.4;
}

.model-id-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .runtime-card__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
  .model-hero__search {
    width: 100%;
  }
}
</style>

<style>
/* 弹窗内容区锁定，避免选中 Logo 时整页跟着抖 */
.model-config-dialog .el-dialog__body {
  overflow-anchor: none;
  overflow-x: hidden;
}
.model-config-dialog .el-form-item__content {
  max-width: 100%;
}
</style>
