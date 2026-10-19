<script setup lang="ts">
/**
 * 知识库管理：文档列表 / 文本导入 / 文件上传 / 检索与分片配置 / 分片查看。
 * KB-20：中间栏「检索与分片」可热更新参数，免重启。
 * KB-01：同面板可开关混合检索（BM25∪向量）与 RRF 常数。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addDocumentText,
  getDocumentOriginal,
  getKbSettings,
  listChunks,
  listDocuments,
  originalDownloadUrl,
  rebuildChunks,
  removeDocument,
  updateKbSettings,
  uploadKbFile,
  type KbChunk,
  type KbDocument,
  type KbSettings,
} from '@/api/kb'
import EditionGate from '@/components/commercial/EditionGate.vue'

const docs = ref<KbDocument[]>([])
const loadingDocs = ref(false)
const selected = ref<string>('')
const filter = ref('')

const chunks = ref<KbChunk[]>([])
const loadingChunks = ref(false)
const chunkTotal = ref(0)
const chunkPage = ref(1)
const chunkPageSize = ref(30)

const detailVisible = ref(false)
const detailChunk = ref<KbChunk | null>(null)

const originalVisible = ref(false)
const originalLoading = ref(false)
const originalText = ref('')
const originalMeta = ref<{ filename?: string; size?: number; is_text?: boolean }>({})

const textFilename = ref('note.md')
const textContent = ref('')
const uploading = ref(false)

const settingsLoading = ref(false)
const settingsSaving = ref(false)
const settingsNotes = ref<KbSettings['notes']>({})
const form = reactive({
  default_k: 5,
  max_search_results: 10,
  min_source_similarity: 0.6,
  chunk_size: 800,
  chunk_overlap: 120,
  hybrid_enabled: true,
  rrf_k: 60,
  max_rerank_candidates: 8,
})

const filteredDocs = computed(() => {
  const q = filter.value.trim().toLowerCase()
  if (!q) return docs.value
  return docs.value.filter((d) => d.filename.toLowerCase().includes(q))
})

const selectedDoc = computed(() => docs.value.find((d) => d.filename === selected.value) || null)

async function refreshDocs() {
  loadingDocs.value = true
  try {
    const data = await listDocuments()
    docs.value = data.documents || []
    if (selected.value && !docs.value.some((d) => d.filename === selected.value)) {
      selected.value = ''
      chunks.value = []
    }
  } catch (err) {
    ElMessage.error((err as Error).message || '加载文档失败')
  } finally {
    loadingDocs.value = false
  }
}

async function refreshChunks() {
  if (!selected.value) {
    chunks.value = []
    chunkTotal.value = 0
    return
  }
  loadingChunks.value = true
  try {
    const data = await listChunks({
      filename: selected.value,
      pageIndex: chunkPage.value,
      pageSize: chunkPageSize.value,
    })
    chunks.value = data.chunks || []
    chunkTotal.value = Number(data.total ?? data.count ?? chunks.value.length) || 0
  } catch (err) {
    ElMessage.error((err as Error).message || '加载分片失败')
  } finally {
    loadingChunks.value = false
  }
}

watch(selected, () => {
  chunkPage.value = 1
  detailVisible.value = false
  detailChunk.value = null
  refreshChunks()
})

function openChunkDetail(chunk: KbChunk) {
  detailChunk.value = chunk
  detailVisible.value = true
}

function formatBytes(n?: number) {
  const v = Number(n) || 0
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  return `${(v / (1024 * 1024)).toFixed(1)} MB`
}

async function viewOriginal(filename: string) {
  originalLoading.value = true
  originalVisible.value = true
  originalText.value = ''
  originalMeta.value = {}
  try {
    const data = await getDocumentOriginal(filename)
    originalMeta.value = {
      filename: data.filename,
      size: data.size,
      is_text: data.is_text,
    }
    if (data.is_text && data.content != null) {
      originalText.value = String(data.content)
    } else {
      originalText.value = ''
      // 二进制直接走下载
      window.open(originalDownloadUrl(filename), '_blank')
      originalVisible.value = false
      ElMessage.info('已开始下载原文件')
    }
  } catch (err) {
    originalVisible.value = false
    ElMessage.error((err as Error).message || '原文件不存在或无法读取')
  } finally {
    originalLoading.value = false
  }
}

function downloadOriginal(filename: string) {
  window.open(originalDownloadUrl(filename), '_blank')
}

async function loadSettings() {
  settingsLoading.value = true
  try {
    const data = await getKbSettings()
    const s = data.settings
    form.default_k = s.default_k
    form.max_search_results = s.max_search_results
    form.min_source_similarity = s.min_source_similarity
    form.chunk_size = s.chunk_size
    form.chunk_overlap = s.chunk_overlap
    form.hybrid_enabled = s.hybrid_enabled !== false
    form.rrf_k = s.rrf_k ?? 60
    form.max_rerank_candidates = s.max_rerank_candidates ?? 8
    settingsNotes.value = s.notes || {}
  } catch (err) {
    ElMessage.error((err as Error).message || '加载检索配置失败')
  } finally {
    settingsLoading.value = false
  }
}

async function onSaveSettings() {
  settingsSaving.value = true
  try {
    const data = await updateKbSettings({ ...form })
    const s = data.settings
    form.default_k = s.default_k
    form.max_search_results = s.max_search_results
    form.min_source_similarity = s.min_source_similarity
    form.chunk_size = s.chunk_size
    form.chunk_overlap = s.chunk_overlap
    form.hybrid_enabled = s.hybrid_enabled !== false
    form.rrf_k = s.rrf_k ?? 60
    form.max_rerank_candidates = s.max_rerank_candidates ?? 8
    settingsNotes.value = s.notes || {}
    ElMessage.success('已保存到数据库：检索参数立即生效；分片参数对新导入/重建生效')
  } catch (err) {
    ElMessage.error((err as Error).message || '保存失败')
  } finally {
    settingsSaving.value = false
  }
}

async function onAddText() {
  const filename = textFilename.value.trim()
  const text = textContent.value
  if (!filename || !text.trim()) {
    ElMessage.warning('请填写文件名与文本内容')
    return
  }
  try {
    const res = await addDocumentText(filename, text)
    ElMessage.success(`已导入，新增分片 ${res.chunks_added ?? '-'}`)
    textContent.value = ''
    await refreshDocs()
    selected.value = filename
  } catch (err) {
    ElMessage.error((err as Error).message || '导入失败')
  }
}

async function onUpload(file: File) {
  uploading.value = true
  try {
    const res = await uploadKbFile(file)
    ElMessage.success(`上传成功，新增分片 ${res.chunks_added ?? '-'}`)
    await refreshDocs()
    selected.value = file.name
  } catch (err) {
    ElMessage.error((err as Error).message || '上传失败')
  } finally {
    uploading.value = false
  }
  return false
}

async function onUploadRequest(opt: { file: File | Blob }) {
  return onUpload(opt.file as File)
}

async function onRemove(filename: string) {
  try {
    await ElMessageBox.confirm(`确认删除文档「${filename}」及其全部分片？`, '删除确认', {
      type: 'warning',
    })
    await removeDocument(filename)
    ElMessage.success('已删除')
    if (selected.value === filename) selected.value = ''
    await refreshDocs()
  } catch {
    /* 取消或失败已提示 */
  }
}

async function onRebuild(filename: string) {
  try {
    const res = await rebuildChunks(filename)
    ElMessage.success(`重建完成，分片 ${res.chunks_added ?? '-'}`)
    await refreshDocs()
    await refreshChunks()
  } catch (err) {
    ElMessage.error((err as Error).message || '重建失败')
  }
}

onMounted(() => {
  refreshDocs()
  loadSettings()
})
</script>

<template>
  <div class="kb-layout">
    <aside class="page-card kb-tree">
      <div class="kb-tree__head">
        <h3>文档</h3>
        <el-button size="small" :loading="loadingDocs" @click="refreshDocs">刷新</el-button>
      </div>
      <el-input v-model="filter" size="small" clearable placeholder="筛选文件名" style="margin-bottom: 10px" />
      <el-scrollbar height="calc(100vh - 240px)">
        <div
          v-for="doc in filteredDocs"
          :key="doc.filename"
          class="kb-doc"
          :class="{ active: selected === doc.filename }"
          @click="selected = doc.filename"
        >
          <div class="kb-doc__name">{{ doc.filename }}</div>
          <div class="kb-doc__meta">
            {{ doc.chunk_count }} 片 · {{ doc.char_count }} 字
            <span v-if="doc.has_original" class="kb-doc__orig">· 有原文件</span>
          </div>
        </div>
        <p v-if="!filteredDocs.length" class="muted">暂无文档</p>
      </el-scrollbar>
    </aside>

    <section class="page-card kb-center">
      <h3>导入 / 配置</h3>
      <el-tabs>
        <el-tab-pane label="文本导入">
          <el-form label-position="top">
            <el-form-item label="文件名">
              <el-input v-model="textFilename" placeholder="例如 guide.md" />
            </el-form-item>
            <el-form-item label="文本内容">
              <el-input v-model="textContent" type="textarea" :rows="10" placeholder="粘贴知识文本…" />
            </el-form-item>
            <el-button type="primary" @click="onAddText">写入知识库</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="文件上传">
          <el-upload drag :show-file-list="false" :http-request="onUploadRequest" :disabled="uploading">
            <div class="el-upload__text">拖拽文件到此处，或<em>点击上传</em></div>
          </el-upload>
        </el-tab-pane>
        <el-tab-pane label="检索与分片">
          <p class="hint">{{ settingsNotes?.search || '检索参数保存后立即生效，无需重启。' }}</p>
          <p class="hint">{{ settingsNotes?.chunk || '分片参数仅对新导入或重建分片生效。' }}</p>
          <el-form v-loading="settingsLoading" label-position="top" class="settings-form">
            <div class="settings-grid">
              <el-form-item label="默认召回数 default_k">
                <el-input-number v-model="form.default_k" :min="1" :max="50" controls-position="right" />
              </el-form-item>
              <el-form-item label="最大召回数 max_search_results">
                <el-input-number v-model="form.max_search_results" :min="1" :max="100" controls-position="right" />
              </el-form-item>
              <el-form-item label="候选过滤线 min_source_similarity">
                <el-input-number
                  v-model="form.min_source_similarity"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  :precision="2"
                  controls-position="right"
                />
              </el-form-item>
              <el-form-item label="分片长度 chunk_size">
                <el-input-number v-model="form.chunk_size" :min="100" :max="8000" :step="50" controls-position="right" />
              </el-form-item>
              <el-form-item label="分片重叠 chunk_overlap">
                <el-input-number v-model="form.chunk_overlap" :min="0" :max="7999" :step="10" controls-position="right" />
              </el-form-item>
              <el-form-item label="混合检索 hybrid_enabled">
                <el-switch v-model="form.hybrid_enabled" active-text="BM25∪向量" inactive-text="仅向量" />
              </el-form-item>
              <el-form-item label="RRF 常数 rrf_k">
                <el-input-number
                  v-model="form.rrf_k"
                  :min="1"
                  :max="200"
                  :disabled="!form.hybrid_enabled"
                  controls-position="right"
                />
              </el-form-item>
              <el-form-item label="重排候选上限 max_rerank_candidates">
                <el-input-number
                  v-model="form.max_rerank_candidates"
                  :min="1"
                  :max="100"
                  controls-position="right"
                />
              </el-form-item>
              <el-form-item label="分片策略">
                <el-input model-value="固定长度（社区）" disabled />
              </el-form-item>
            </div>
            <p class="hint subtle">
              {{
                settingsNotes?.threshold ||
                '候选过滤线：内部排序分低于它的候选直接丢弃，0 表示不过滤；它不是正确率。候选最终能否作为来源由证据门槛决定。设置保存在数据库。'
              }}
            </p>
            <p class="hint subtle">{{ settingsNotes?.persist || '' }}</p>
            <p class="hint subtle">{{ settingsNotes?.hybrid || '开启混合检索后：BM25 字面召回与向量召回经 RRF 融合，再交重排；单通道失败自动降级。' }}</p>
            <p class="hint subtle">{{ settingsNotes?.rerank || '重排候选上限越小，CPU 上交叉编码器越快；过大易拖垮检索延迟。' }}</p>
            <el-button type="primary" :loading="settingsSaving" @click="onSaveSettings">保存并生效</el-button>
            <el-button :disabled="settingsLoading || settingsSaving" @click="loadSettings">重新读取</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div v-if="selectedDoc" class="kb-selected">
        <h4>当前文档：{{ selectedDoc.filename }}</h4>
        <div class="kb-selected__actions">
          <el-button
            v-if="selectedDoc.has_original"
            size="small"
            type="primary"
            plain
            @click="viewOriginal(selectedDoc.filename)"
          >
            查看原文件
          </el-button>
          <el-button
            v-if="selectedDoc.has_original"
            size="small"
            @click="downloadOriginal(selectedDoc.filename)"
          >
            下载原文件
          </el-button>
          <el-button size="small" @click="onRebuild(selectedDoc.filename)">重建分片</el-button>
          <el-button size="small" type="danger" plain @click="onRemove(selectedDoc.filename)">删除</el-button>
        </div>
        <p v-if="selectedDoc.has_original" class="hint subtle">
          原文件约 {{ formatBytes(selectedDoc.original_size) }}，保存在知识库 documents 目录。
        </p>
        <p v-else class="hint subtle">该文档尚无落盘原文件（历史导入）；重新上传或文本导入后会保存。</p>
      </div>

      <EditionGate
        style="margin-top: 20px"
        title="多租户知识库树"
        description="按租户切换知识库隔离空间、配额与导入策略。"
        community-note="单实例文档列表"
        commercial-note="租户切换 + 隔离索引"
      />
    </section>

    <aside class="page-card kb-status">
      <div class="kb-tree__head">
        <h3>分片详情</h3>
        <el-button size="small" :disabled="!selected" :loading="loadingChunks" @click="refreshChunks">刷新</el-button>
      </div>
      <p v-if="!selected" class="muted">选择左侧文档查看分片。</p>
      <template v-else>
        <p class="hint subtle">共 {{ chunkTotal }} 片，点击条目查看完整内容。</p>
        <el-scrollbar height="calc(100vh - 280px)">
          <button
            v-for="chunk in chunks"
            :key="chunk.id"
            type="button"
            class="kb-chunk"
            @click="openChunkDetail(chunk)"
          >
            <div class="kb-chunk__head">
              <span class="kb-chunk__id">#{{ (chunk.chunk_index ?? 0) + 1 }}</span>
              <span class="kb-chunk__meta">{{ chunk.char_count ?? chunk.text?.length ?? 0 }} 字 · id={{ chunk.id }}</span>
            </div>
            <pre>{{ chunk.preview || chunk.text }}</pre>
          </button>
          <p v-if="!chunks.length && !loadingChunks" class="muted">无分片</p>
        </el-scrollbar>
        <el-pagination
          v-if="chunkTotal > chunkPageSize"
          class="kb-chunk__pager"
          small
          layout="prev, pager, next"
          :total="chunkTotal"
          :page-size="chunkPageSize"
          :current-page="chunkPage"
          @current-change="(p: number) => { chunkPage = p; refreshChunks() }"
        />
      </template>
    </aside>

    <el-dialog
      v-model="detailVisible"
      :title="detailChunk ? `分片 #${(detailChunk.chunk_index ?? 0) + 1}` : '分片详情'"
      width="720px"
      destroy-on-close
    >
      <p v-if="detailChunk" class="hint subtle">
        文档：{{ detailChunk.filename }} · 全局 id={{ detailChunk.id }} ·
        {{ detailChunk.char_count ?? detailChunk.text?.length ?? 0 }} 字
      </p>
      <pre class="kb-chunk__full">{{ detailChunk?.text }}</pre>
    </el-dialog>

    <el-dialog
      v-model="originalVisible"
      :title="originalMeta.filename ? `原文件：${originalMeta.filename}` : '原文件'"
      width="800px"
      destroy-on-close
    >
      <div v-loading="originalLoading">
        <p class="hint subtle">大小 {{ formatBytes(originalMeta.size) }}</p>
        <pre class="kb-chunk__full">{{ originalText }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.kb-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}
.kb-tree__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.kb-tree__head h3,
.kb-center h3,
.kb-status h3 {
  margin: 0;
  font-size: 16px;
}
.kb-doc {
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
}
.kb-doc:hover {
  background: var(--color-primary-subtle);
}
.kb-doc.active {
  border-color: var(--color-primary);
  background: var(--color-primary-subtle);
}
.kb-doc__name {
  font-weight: 600;
  font-size: 13px;
  word-break: break-all;
}
.kb-doc__meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.kb-doc__orig {
  color: var(--color-link, #2563eb);
}
.kb-selected {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}
.kb-selected h4 {
  margin: 0 0 10px;
}
.kb-selected__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.kb-chunk {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  border-top: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px 8px;
  margin: 0;
  background: transparent;
  cursor: pointer;
}
.kb-chunk:hover {
  background: var(--color-bg-subtle, #f8fafc);
  border-color: var(--color-border);
}
.kb-chunk__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.kb-chunk__id {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.kb-chunk__meta {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.kb-chunk pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.kb-chunk__full {
  margin: 0;
  max-height: 60vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  background: var(--color-bg-subtle, #f8fafc);
  padding: 12px;
  border-radius: 8px;
}
.kb-chunk__pager {
  margin-top: 10px;
  justify-content: center;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
}
.hint {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.hint.subtle {
  margin-bottom: 14px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 16px;
}
.settings-form :deep(.el-input-number) {
  width: 100%;
}
@media (max-width: 1100px) {
  .kb-layout {
    grid-template-columns: 1fr;
  }
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
