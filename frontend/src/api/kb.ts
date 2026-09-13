/**
 * 知识库文档 / 分片 / 检索配置 API。
 */
import { del, get, post, put } from '@/utils/request'

export interface KbDocument {
  filename: string
  chunk_count: number
  char_count: number
}

export interface KbChunk {
  id: number
  filename?: string
  text?: string
  chunk_index?: number
}

/** KB-20：检索与固定长度分片参数 */
export interface KbSettings {
  default_k: number
  max_search_results: number
  min_source_similarity: number
  chunk_size: number
  chunk_overlap: number
  chunking_strategy?: string
  notes?: {
    search?: string
    chunk?: string
    threshold?: string
  }
}

export function listDocuments() {
  return get<{ ok: boolean; count: number; documents: KbDocument[] }>('/kb/documents')
}

export function listChunks(params: {
  pageIndex?: number
  pageSize?: number
  filename?: string
  q?: string
}) {
  return get<{ ok: boolean; count: number; chunks: KbChunk[] }>('/kb/chunks', params)
}

export function addDocumentText(filename: string, text: string) {
  return post<{ ok: boolean; chunks_added?: number }>('/kb/document', { filename, text })
}

export function uploadKbFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  return post<{ ok: boolean; chunks_added?: number }>('/kb/file', form)
}

export function removeDocument(filename: string) {
  return del<{ ok: boolean; chunks_removed?: number }>(`/kb/document/${encodeURIComponent(filename)}`)
}

export function rebuildChunks(filename: string) {
  return post<{ ok: boolean; chunks_added?: number }>('/kb/chunks/rebuild', { filename })
}

export function getKbSettings() {
  return get<{ ok: boolean; settings: KbSettings }>('/kb/settings')
}

export function updateKbSettings(payload: Partial<KbSettings>) {
  return put<{ ok: boolean; settings: KbSettings }>('/kb/settings', payload)
}
