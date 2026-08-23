/**
 * 问答相关类型与 SSE 流式调用。
 */
export interface QueryBody {
  query: string
  k?: number
  deep_think?: boolean
  stream?: boolean
  user_id?: string
  session_id?: string
  generate_answer?: boolean
  relevance_threshold?: number | null
  model_config_id?: number
  use_default_model_config?: boolean
  enable_mcp_auto?: boolean
}

export interface SourceResult {
  filename?: string
  similarity?: number
  distance?: number
  text?: string
  preview_text?: string
}

export interface StreamHandlers {
  onMeta?: (payload: {
    results?: SourceResult[]
    session_id?: string
    user_id?: string
    mcp_execution?: unknown
  }) => void
  onDelta?: (delta: string) => void
  onThinkingDelta?: (delta: string) => void
  onDone?: (payload: {
    answer?: string
    thinking?: string
    thinking_summary?: string
    finish_reason?: string
  }) => void
  signal?: AbortSignal
}

/**
 * 解析 SSE 文本块并回调。
 * @returns 是否已收到正式结束事件 `done`
 */
function dispatchSseBlock(block: string, handlers: StreamHandlers): boolean {
  const lines = block.split(/\r?\n/)
  let eventType = 'message'
  const dataLines: string[] = []
  for (const raw of lines) {
    // 去掉行尾 \r，否则 JSON.parse 会直接挂掉（点「停止」才露出内容就是这个）
    const line = raw.replace(/\r$/, '').trimEnd()
    if (!line) continue
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  if (!dataLines.length) return false
  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(dataLines.join('\n'))
  } catch {
    return false
  }
  if (eventType === 'meta') {
    handlers.onMeta?.(payload as Parameters<NonNullable<StreamHandlers['onMeta']>>[0])
  } else if (eventType === 'delta') {
    const delta = String(payload.delta || '')
    if (delta) handlers.onDelta?.(delta)
  } else if (eventType === 'thinking_delta') {
    const delta = String(payload.delta || '')
    if (delta) handlers.onThinkingDelta?.(delta)
  } else if (eventType === 'done') {
    handlers.onDone?.(payload as Parameters<NonNullable<StreamHandlers['onDone']>>[0])
    return true
  } else if (eventType === 'error') {
    const message = String(payload.message || payload.error || '流式问答失败')
    throw new Error(message)
  }
  return false
}

function queryStreamUrl(): string {
  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const direct = String(import.meta.env.VITE_PROXY_TARGET || '').replace(/\/$/, '')
  // 开发态直连后端，绕开 Vite 代理对 SSE 的缓冲
  if (import.meta.env.DEV && direct) {
    return `${direct}${apiBase}/query?stream=1`
  }
  return `${apiBase}/query?stream=1`
}

/**
 * 用 XHR 拉 SSE：onprogress 能边下边解析，比 fetch+ReadableStream 稳。
 * 收到 done 立刻结束；中止时也会先冲刷剩余缓冲。
 */
export function streamQuery(body: QueryBody, handlers: StreamHandlers = {}): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    let seen = 0
    let buffer = ''
    let finished = false
    let settled = false

    const fail = (err: Error) => {
      if (settled) return
      settled = true
      reject(err)
    }

    const succeed = () => {
      if (settled) return
      settled = true
      resolve()
    }

    const consume = (chunk: string) => {
      if (finished || !chunk) return
      buffer += chunk
      // 同时兼容 \n\n 与 \r\n\r\n
      const parts = buffer.split(/\r?\n\r?\n/)
      buffer = parts.pop() || ''
      for (const part of parts) {
        if (!part.trim()) continue
        if (dispatchSseBlock(part, handlers)) {
          finished = true
          try {
            xhr.abort()
          } catch {
            // ignore
          }
          succeed()
          return
        }
      }
    }

    const flushTail = () => {
      if (finished || !buffer.trim()) return
      if (dispatchSseBlock(buffer, handlers)) {
        finished = true
      }
      buffer = ''
    }

    xhr.open('POST', queryStreamUrl(), true)
    xhr.setRequestHeader('Content-Type', 'application/json')
    xhr.setRequestHeader('Accept', 'text/event-stream')
    xhr.setRequestHeader('Cache-Control', 'no-cache')
    xhr.responseType = 'text'

    xhr.onprogress = () => {
      try {
        const text = String(xhr.responseText || '')
        if (text.length <= seen) return
        const chunk = text.slice(seen)
        seen = text.length
        consume(chunk)
      } catch (err) {
        fail(err as Error)
      }
    }

    xhr.onload = () => {
      try {
        const text = String(xhr.responseText || '')
        if (text.length > seen) {
          consume(text.slice(seen))
          seen = text.length
        }
        flushTail()
        if (xhr.status >= 400) {
          fail(new Error(text || `请求失败（${xhr.status}）`))
          return
        }
        succeed()
      } catch (err) {
        fail(err as Error)
      }
    }

    xhr.onerror = () => fail(new Error('网络错误，流式问答中断'))
    xhr.onabort = () => {
      try {
        flushTail()
      } catch {
        // ignore
      }
      if (finished) {
        succeed()
        return
      }
      const err = new Error('Aborted')
      err.name = 'AbortError'
      fail(err)
    }

    const onAbort = () => {
      try {
        xhr.abort()
      } catch {
        // ignore
      }
    }
    if (handlers.signal) {
      if (handlers.signal.aborted) {
        onAbort()
        return
      }
      handlers.signal.addEventListener('abort', onAbort, { once: true })
    }

    xhr.send(
      JSON.stringify({
        ...body,
        stream: true,
        deep_think: Boolean(body.deep_think),
        generate_answer: body.generate_answer !== false,
      }),
    )
  })
}

export async function createSession(userId: string): Promise<string> {
  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const resp = await fetch(`${apiBase}/session?user_id=${encodeURIComponent(userId)}`)
  const payload = await resp.json().catch(() => ({}))
  const data = payload?.data ?? payload
  const sessionId = String(data?.session_id || data?.sessionId || '').trim()
  if (!sessionId) {
    throw new Error('未能创建会话')
  }
  return sessionId
}
