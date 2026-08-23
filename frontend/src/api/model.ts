/**
 * 聊天模型配置 API（对应旧版 /ui/model.html）。
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
}

export interface ModelProvider {
  name: string
  base_url?: string
  requires_api_key?: boolean
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

export function getDefaultModelConfig() {
  return get<{ ok: boolean; config?: ModelConfig | null }>('/model/config/default')
}

export function createModelConfig(body: ModelConfigPayload) {
  return post<{ ok: boolean }>('/model/config', body)
}

export function updateModelConfig(id: number, body: Partial<ModelConfigPayload>) {
  return put<{ ok: boolean }>(`/model/config/${id}`, body)
}

export function deleteModelConfig(id: number) {
  return del<{ ok: boolean }>(`/model/config/${id}`)
}

export function setDefaultModelConfig(id: number) {
  return post<{ ok: boolean }>(`/model/config/${id}/default`, {})
}

export function testModelConfig(body: { config_id?: number; name?: string; config?: ModelConfigPayload }) {
  return post<{ ok: boolean; success?: boolean; message?: string; error?: string; latency_ms?: number }>(
    '/model/config/test',
    body,
  )
}

export function bootstrapModelConfigs() {
  return post<{ ok: boolean; created?: number; skipped?: number; message?: string }>(
    '/model/config/bootstrap',
    {},
  )
}
