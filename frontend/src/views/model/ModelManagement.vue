<script setup lang="ts">
/**
 * 模型管理：配置列表 / 增删改 / 设默认 / 连通性测试 / 初始化预设。
 * 对齐旧版 archive/web/model.html 能力。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  bootstrapModelConfigs,
  createModelConfig,
  deleteModelConfig,
  listModelConfigs,
  listModelProviders,
  setDefaultModelConfig,
  testModelConfig,
  updateModelConfig,
  type ModelConfig,
  type ModelConfigPayload,
  type ModelProvider,
} from '@/api/model'

const loading = ref(false)
const rows = ref<ModelConfig[]>([])
const providers = ref<ModelProvider[]>([])

const dialogVisible = ref(false)
const dialogTitle = ref('新增模型配置')
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  provider: '',
  base_url: '',
  model_name: '',
  api_key: '',
  temperature: 0.7,
  max_tokens: undefined as number | undefined,
  timeout: 30,
  description: '',
  is_active: true,
  is_default: false,
})

function resetForm() {
  editingId.value = null
  form.name = ''
  form.provider = providers.value[0]?.name || ''
  form.base_url = providers.value[0]?.base_url || ''
  form.model_name = ''
  form.api_key = ''
  form.temperature = 0.7
  form.max_tokens = undefined
  form.timeout = 30
  form.description = ''
  form.is_active = true
  form.is_default = false
}

function onProviderChange(name: string) {
  const hit = providers.value.find((p) => p.name === name)
  if (hit?.base_url && !editingId.value) {
    form.base_url = hit.base_url
  } else if (hit?.base_url && !form.base_url.trim()) {
    form.base_url = hit.base_url
  }
}

async function refreshProviders() {
  try {
    const data = await listModelProviders()
    providers.value = data.providers || []
  } catch (err) {
    ElMessage.error((err as Error).message || '加载服务商失败（需启用数据库后端）')
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

function openCreate() {
  resetForm()
  dialogTitle.value = '新增模型配置'
  dialogVisible.value = true
}

function openEdit(row: ModelConfig) {
  editingId.value = row.id
  dialogTitle.value = '编辑模型配置'
  form.name = row.name || ''
  form.provider = row.provider || ''
  form.base_url = row.base_url || ''
  form.model_name = row.model_name || ''
  form.api_key = ''
  form.temperature = row.temperature ?? 0.7
  form.max_tokens = row.max_tokens ?? undefined
  form.timeout = row.timeout ?? 30
  form.description = row.description || ''
  form.is_active = Boolean(row.is_active)
  form.is_default = Boolean(row.is_default)
  dialogVisible.value = true
}

function buildPayload(): ModelConfigPayload {
  const body: ModelConfigPayload = {
    name: form.name.trim(),
    provider: form.provider.trim(),
    base_url: form.base_url.trim(),
    model_name: form.model_name.trim(),
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
  return body
}

async function onSave() {
  const body = buildPayload()
  if (!body.name || !body.provider || !body.base_url || !body.model_name) {
    ElMessage.warning('名称、服务商、接口地址、模型名称不能为空')
    return
  }
  saving.value = true
  try {
    if (editingId.value != null) {
      await updateModelConfig(editingId.value, body)
      ElMessage.success('模型配置已更新')
    } else {
      await createModelConfig(body)
      ElMessage.success('模型配置已新增')
    }
    dialogVisible.value = false
    await refreshConfigs()
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
    await setDefaultModelConfig(row.id)
    ElMessage.success(`已将「${row.name}」设为默认`)
    await refreshConfigs()
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
  await refreshConfigs()
})
</script>

<template>
  <div class="page-card model-page">
    <header class="model-head">
      <div>
        <h2>模型控制管理</h2>
        <p>管理聊天模型配置、切换默认配置，并进行连通性测试。</p>
      </div>
      <div class="model-actions">
        <el-button type="primary" @click="openCreate">新增模型</el-button>
        <el-button @click="refreshConfigs">刷新配置</el-button>
        <el-button @click="onBootstrap">初始化预设配置</el-button>
      </div>
    </header>

    <el-table v-loading="loading" :data="rows" stripe empty-text="暂无模型配置" style="width: 100%">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="provider" label="服务商" width="120" />
      <el-table-column prop="model_name" label="模型" min-width="140" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="warning" size="small">是</el-tag>
          <span v-else>否</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" @click="onTest(row)">测试</el-button>
          <el-button link type="warning" :disabled="row.is_default" @click="onSetDefault(row)">
            设默认
          </el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="my-model" />
        </el-form-item>
        <el-form-item label="服务商" required>
          <el-select v-model="form.provider" style="width: 100%" @change="onProviderChange">
            <el-option v-for="p in providers" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口地址" required>
          <el-input v-model="form.base_url" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="模型名称" required>
          <el-input v-model="form.model_name" placeholder="gpt-4o-mini" />
        </el-form-item>
        <el-form-item label="API 密钥">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="editingId ? '留空表示不修改' : '可留空'"
          />
        </el-form-item>
        <el-form-item label="temperature">
          <el-input-number v-model="form.temperature" :step="0.1" :min="0" :max="2" />
        </el-form-item>
        <el-form-item label="max_tokens">
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
  gap: 16px;
  min-height: calc(100vh - 120px);
}

.model-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.model-head h2 {
  margin: 0 0 6px;
  font-size: 1.25rem;
}

.model-head p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 0.9rem;
}

.model-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
