/**
 * 问答历史：按会话分组列表 / 删除会话。
 */
import { del, get } from '@/utils/request'
import type { SourceResult } from '@/api/query'

export interface HistoryItem {
  id?: number
  action?: string
  timestamp?: string
  session_id?: string
  user_id?: string | null
  request?: {
    query?: string
    session_id?: string
    user_id?: string
    deep_think?: boolean
    generate_answer?: boolean
    k?: number
    [key: string]: unknown
  }
  response?: {
    answer?: string
    thinking?: string
    thinking_summary?: string
    results?: SourceResult[]
    finish_reason?: string
    messages?: Array<{ role?: string; content?: string }>
    [key: string]: unknown
  }
  error?: string | null
  /** 部分存储把摘要放在条目根上 */
  thinking_summary?: string
}

export interface HistorySession {
  session_id: string
  first_query?: string
  timestamp?: string
  user_id?: string | null
  count?: number
  items?: HistoryItem[]
}

export function listHistorySessions(params?: { limit?: number; action?: string }) {
  return get<{ ok: boolean; sessions: HistorySession[] }>('/history', {
    group_by_session: true,
    limit: params?.limit ?? 50,
    action: params?.action ?? 'query',
  })
}

export function deleteHistorySession(sessionId: string) {
  return del<{ ok: boolean; removed?: number }>(`/session/${encodeURIComponent(sessionId)}`)
}
