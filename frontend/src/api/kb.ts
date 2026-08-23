/**
 * 知识库文档 / 分片 API。
 */
import { del, get, post } from '@/utils/request'

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
