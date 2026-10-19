/**
 * 模型配置 API：Embedding / Reranker / 知识库分析（chat）统一列表。
 */
import { del, get, post, put } from '@/utils/request'

export interface ModelConfig {
  id: number
  name: string
  provider: string
  base_url: string
  model_name: string
  model_type?: string
  temperature?: number
  max_tokens?: number | null
  timeout?: number
  is_active?: boolean
  is_default?: boolean
  description?: string | null
  api_key_set?: boolean
  dimension?: number | null
  max_input_length?: number | null
}

export interface ModelProvider {
  name: string
  base_url?: string
  requires_api_key?: boolean
  local_load?: boolean
  model_types?: string[]
  label?: string
}

export interface ModelConfigPayload {
  name: string
  provider: string
  base_url: string
  model_name: string
  api_key?: string
  model_type?: string
  temperature?: number
  max_tokens?: number | null
  timeout?: number
  is_active?: boolean
  is_default?: boolean
  description?: string | null
  dimension?: number | null
  max_input_length?: number | null
}

export function listModelConfigs(params?: {
  provider?: string
  is_active?: boolean
  model_type?: string
}) {
  return get<{ ok: boolean; configs: ModelConfig[]; count: number }>('/model/configs', params)
}

export function listModelProviders() {
  return get<{ ok: boolean; providers: ModelProvider[] }>('/model/providers')
}

export interface LocalHfModel {
  id: string
  label: string
  kinds?: string[]
  cached?: boolean
  recommended?: boolean
  path?: string
}

export function listLocalHfModels(modelType?: string) {
  return get<{ ok: boolean; models: LocalHfModel[]; cache_dir?: string; count?: number }>(
    '/model/local-models',
    modelType ? { model_type: modelType } : undefined,
  )
}

export function getDefaultModelConfig() {
  return get<{ ok: boolean; config?: ModelConfig | null }>('/model/config/default')
}

export type RetrievalBackend = 'local_hf' | 'openai_compat'

export function createModelConfig(body: ModelConfigPayload) {
  return post<{
    ok: boolean
    config?: ModelConfig
    runtime?: {
      ok?: boolean
      model?: string
      backend?: RetrievalBackend | string
      warnings?: string[]
      error?: string
    }
  }>('/model/config', body)
}

export function updateModelConfig(id: number, body: Partial<ModelConfigPayload>) {
  return put<{
    ok: boolean
    config?: ModelConfig
    runtime?: {
      ok?: boolean
      model?: string
      backend?: RetrievalBackend | string
      warnings?: string[]
      error?: string
    }
  }>(`/model/config/${id}`, body)
}

export function deleteModelConfig(id: number) {
  return del<{ ok: boolean }>(`/model/config/${id}`)
}

export function setDefaultModelConfig(id: number) {
  return post<{
    ok: boolean
    default_config_id?: number
    config?: ModelConfig
    runtime?: {
      ok?: boolean
      model?: string
      backend?: RetrievalBackend | string
      warnings?: string[]
      error?: string
    }
  }>(`/model/config/${id}/default`, {})
}

export function testModelConfig(body: { config_id?: number; name?: string; config?: ModelConfigPayload }) {
  return post<{ ok: boolean; success?: boolean; message?: string; error?: string; latency_ms?: number }>(
    '/model/config/test',
    body,
  )
}

export function listRemoteModels(body: {
  provider: string
  base_url: string
  api_key?: string
  timeout?: number
  config_id?: number
}) {
  return post<{
    ok: boolean
    models?: Array<{ id: string; label?: string }>
    count?: number
    provider?: string
    error?: string
  }>('/model/config/list-models', body)
}

export function bootstrapModelConfigs() {
  return post<{ ok: boolean; created?: number; skipped?: number; message?: string }>(
    '/model/config/bootstrap',
    {},
  )
}
