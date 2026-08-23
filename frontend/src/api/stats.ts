/**
 * 统计与探测接口。
 */
import { get } from '@/utils/request'

export interface KbStats {
  chunk_count?: number
  document_count?: number
  index_size?: number
  embedding_model?: string
  [key: string]: unknown
}

export function getStats() {
  return get<{ ok: boolean; stats: KbStats }>('/stats')
}

/** @deprecated 使用 getStats */
export function getStatsProbe() {
  return getStats()
}
