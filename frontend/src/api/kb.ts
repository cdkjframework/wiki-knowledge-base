/**
 * 知识库文档 / 分片 / 检索配置 API。
 */
import { del, get, post, put } from '@/utils/request'

export interface KbDocument {
  filename: string
  chunk_count: number
  char_count: number
  has_original?: boolean
  original_size?: number
}

export interface KbChunk {
  id: number
  chunk_index?: number
  filename?: string
  text?: string
  preview?: string
  char_count?: number
}

/** KB-20 / KB-01：检索、混合召回与固定长度分片参数 */
export interface KbSettings {
  default_k: number
  max_search_results: number
  min_source_similarity: number
  chunk_size: number
  chunk_overlap: number
  hybrid_enabled?: boolean
  rrf_k?: number
  max_rerank_candidates?: number
  chunking_strategy?: string
  notes?: {
    search?: string
    chunk?: string
    threshold?: string
    persist?: string
    hybrid?: string
    rerank?: string
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
  return get<{
    ok: boolean
    count: number
    total?: number
    page_index?: number
    page_size?: number
    chunks: KbChunk[]
  }>('/kb/chunks', params)
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

/** 预览原文件（文本 JSON）；二进制请用 originalDownloadUrl */
export function getDocumentOriginal(filename: string) {
  return get<{
    ok: boolean
    filename: string
    size: number
    is_text: boolean
    content?: string
    content_type?: string
  }>(`/kb/document/${encodeURIComponent(filename)}/original`, { as: 'json' })
}

export function originalDownloadUrl(filename: string) {
  const base = import.meta.env.VITE_API_BASE_URL || '/api'
  return `${base}/kb/document/${encodeURIComponent(filename)}/original`
}
