/**
 * 模型服务商品牌展示：Logo 色、中文名、适用类型。
 * 值与后端 provider 键对齐；仅 UI，不替代 /model/providers。
 */
export type ProviderKind = 'embedding' | 'rerank' | 'chat'

export interface ProviderBrand {
  id: string
  label: string
  /** @deprecated 已改用 SVG 图标，保留兼容 */
  mark?: string
  color: string
  /** 图标前景色，默认白 */
  markColor?: string
  modelTypes: ProviderKind[]
  /** 本地 / 云端分组 */
  group: 'local' | 'china' | 'global'
  /** 选中时预填 */
  defaultBaseUrl?: string
}

export const PROVIDER_BRANDS: ProviderBrand[] = [
  // —— 本地：Embedding / Rerank 仅这些能接 Qwen3 本地权重 ——
  {
    id: 'huggingface',
    label: 'Hugging Face',
    mark: '🤗',
    color: '#FFD21E',
    markColor: '#1a1a1a',
    modelTypes: ['embedding', 'rerank'],
    group: 'local',
    defaultBaseUrl: 'local://huggingface',
  },
  {
    id: 'lm_studio',
    label: 'LM Studio',
    mark: 'LM',
    color: '#6C5CE7',
    modelTypes: ['chat', 'embedding', 'rerank'],
    group: 'local',
    defaultBaseUrl: 'http://127.0.0.1:1234/v1',
  },
  {
    id: 'ollama',
    label: 'Ollama',
    mark: '🦙',
    color: '#0D0D0D',
    // 分析模型用；Embedding/Rerank 本页不展示（仅 HF 本地 Qwen3 系列）
    modelTypes: ['chat'],
    group: 'local',
    defaultBaseUrl: 'http://127.0.0.1:11434/v1',
  },
  // —— 国内云 ——
  {
    id: 'deepseek',
    label: 'DeepSeek',
    mark: 'DS',
    color: '#4D6BFE',
    modelTypes: ['chat'],
    group: 'china',
    defaultBaseUrl: 'https://api.deepseek.com/v1',
  },
  {
    id: 'qwen',
    label: '通义千问（国内）',
    mark: '千',
    color: '#615CED',
    // 云端可接同系 Embedding/Rerank API（仅国内）
    modelTypes: ['chat', 'embedding', 'rerank'],
    group: 'china',
    defaultBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  {
    id: 'dashscope',
    label: '通义千问（国内）',
    mark: '千',
    color: '#615CED',
    modelTypes: ['chat', 'embedding', 'rerank'],
    group: 'china',
    defaultBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  {
    id: 'kimi',
    label: 'Kimi',
    mark: 'K',
    color: '#1A1A1A',
    modelTypes: ['chat'],
    group: 'china',
    defaultBaseUrl: 'https://api.moonshot.cn/v1',
  },
  {
    id: 'moonshot',
    label: 'Kimi',
    mark: 'K',
    color: '#1A1A1A',
    modelTypes: ['chat'],
    group: 'china',
    defaultBaseUrl: 'https://api.moonshot.cn/v1',
  },
  {
    id: 'doubao',
    label: '豆包',
    mark: '豆',
    color: '#3B82F6',
    modelTypes: ['chat'],
    group: 'china',
    defaultBaseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  },
  // —— 国际 ——
  {
    id: 'openai',
    label: 'OpenAI',
    mark: '✦',
    color: '#10A37F',
    modelTypes: ['chat'],
    group: 'global',
    defaultBaseUrl: 'https://api.openai.com/v1',
  },
  {
    id: 'gemini',
    label: 'Gemini',
    mark: '✦',
    color: '#4285F4',
    modelTypes: ['chat'],
    group: 'global',
    defaultBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
  },
  {
    id: 'xai',
    label: 'Grok',
    mark: 'X',
    color: '#1A1A1A',
    modelTypes: ['chat'],
    group: 'global',
    defaultBaseUrl: 'https://api.x.ai/v1',
  },
]

const BRAND_MAP = new Map(PROVIDER_BRANDS.map((b) => [b.id, b]))

export function getProviderBrand(id: string): ProviderBrand {
  const key = String(id || '').trim().toLowerCase()
  return (
    BRAND_MAP.get(key) || {
      id: key || 'unknown',
      label: key || '未知',
      mark: (key || '?').slice(0, 1).toUpperCase(),
      color: '#64748B',
      modelTypes: ['chat', 'embedding', 'rerank'],
      group: 'global',
    }
  )
}

export function brandsForKind(kind: ProviderKind): ProviderBrand[] {
  // dashscope / moonshot 与 qwen / kimi 同品牌，宫格去重
  const seen = new Set<string>()
  const out: ProviderBrand[] = []
  for (const b of PROVIDER_BRANDS) {
    if (!b.modelTypes.includes(kind)) continue
    const dedupeKey = b.label
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)
    out.push(b)
  }
  return out
}

/** 通义国内：共享域名（普通）vs 业务空间/Team 专属域名 */
export const QWEN_CN_SHARED_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
export const QWEN_CN_INTL_HINT = 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
/** Team/业务空间模板；未填 WorkspaceId 时也展示这个，避免和普通接口看起来一样 */
export const QWEN_CN_WORKSPACE_TEMPLATE =
  'https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'

export type QwenCnEndpointMode = 'shared' | 'workspace'

export function isQwenCnProvider(provider: string): boolean {
  const p = String(provider || '').trim().toLowerCase()
  return p === 'qwen' || p === 'dashscope'
}

export function buildQwenCnBaseUrl(mode: QwenCnEndpointMode, workspaceId?: string): string {
  if (mode === 'workspace') {
    const wid = String(workspaceId || '').trim()
    if (!wid || wid === '{WorkspaceId}') return QWEN_CN_WORKSPACE_TEMPLATE
    return `https://${wid}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
  }
  return QWEN_CN_SHARED_BASE
}

/** 从已有 base_url 反推国内普通 / Team（业务空间） */
export function parseQwenCnEndpoint(baseUrl: string): {
  mode: QwenCnEndpointMode
  workspaceId: string
} {
  const raw = String(baseUrl || '').trim()
  if (!raw) return { mode: 'shared', workspaceId: '' }
  // 模板本身也算 Team 模式
  if (raw.includes('{WorkspaceId}') && raw.includes('maas.aliyuncs.com')) {
    return { mode: 'workspace', workspaceId: '' }
  }
  const m = raw.match(
    /^https?:\/\/([a-zA-Z0-9_-]+)\.cn-beijing\.maas\.aliyuncs\.com\/compatible-mode\/v1\/?$/i,
  )
  if (m?.[1]) {
    return { mode: 'workspace', workspaceId: m[1] }
  }
  return { mode: 'shared', workspaceId: '' }
}

/** 保存前：Team 模式必须已替换真实 WorkspaceId */
export function isQwenCnWorkspaceUrlReady(baseUrl: string): boolean {
  const parsed = parseQwenCnEndpoint(baseUrl)
  if (parsed.mode !== 'workspace') return true
  return Boolean(parsed.workspaceId) && !String(baseUrl).includes('{WorkspaceId}')
}
