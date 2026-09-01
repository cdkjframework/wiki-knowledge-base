/**
 * 指标看板接口（KB-11）。
 *
 * 数值全部来自后端读取的 KB-10 评测报告，前端不自己算指标，
 * 免得看板和跑分结果对不上。
 */
import { get } from '@/utils/request'

/** 单个 KPI 卡片；status=unknown 表示还没跑过评测，别当成不达标 */
export interface MetricKpi {
  key: string
  label: string
  value: number | null
  display: string
  target: number
  target_display: string
  direction: 'up' | 'down'
  unit: string
  status: 'pass' | 'fail' | 'unknown'
}

/** 一次评测的摘要，既用于「最近一次」也用于历史列表 */
export interface EvalReportSummary {
  file: string
  generated_at: string
  dataset_path: string
  case_count: number
  failed_count: number
  'recall@3': number | null
  'recall@5': number | null
  'ndcg@10': number | null
  mrr: number | null
  latency_p95_ms: number | null
  total_seconds: number | null
  top_k: number | null
}

export interface MetricsDashboard {
  ok: boolean
  available: boolean
  hint?: string
  kpis: MetricKpi[]
  latest: EvalReportSummary | null
  history: EvalReportSummary[]
}

export function getMetricsDashboard(limit = 20) {
  return get<MetricsDashboard>('/metrics', { limit })
}

export function getEvalReports(limit = 50) {
  return get<{ ok: boolean; reports: EvalReportSummary[] }>('/metrics/reports', { limit })
}
