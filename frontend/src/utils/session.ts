/**
 * 简易会话偏好（本地存储）。
 */
const USER_KEY = 'wiki_kb_user_id'
const SESSION_KEY = 'wiki_kb_session_id'

export function loadUserId(defaultValue = 'local-user'): string {
  return localStorage.getItem(USER_KEY)?.trim() || defaultValue
}

export function saveUserId(userId: string) {
  localStorage.setItem(USER_KEY, userId.trim())
}

export function loadSessionId(): string {
  return localStorage.getItem(SESSION_KEY)?.trim() || ''
}

export function saveSessionId(sessionId: string) {
  if (sessionId) {
    localStorage.setItem(SESSION_KEY, sessionId.trim())
  } else {
    localStorage.removeItem(SESSION_KEY)
  }
}
