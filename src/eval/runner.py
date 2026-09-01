"""
跑分执行与报告落盘。

检索入口用回调注入（`SearchFn`），跑分逻辑就不绑死 KnowledgeBase，
单测可以喂假检索器，KB-11 看板将来也能直接读这里产出的报告 JSON。
"""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

from .dataset import GoldenCase
from .metrics import (
    hit_at_k,
    matched_flags,
    mean,
    ndcg_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

REPORT_SCHEMA = "kb-eval-report/1"
DEFAULT_KS: Sequence[int] = (1, 3, 5, 10)
DEFAULT_NDCG_K = 10

# 给定 query 与 top_k，返回按名次排列的文档标识
SearchFn = Callable[[str, int], Sequence[str]]


def default_report_dir(root: Path | None = None) -> Path:
    """报告默认落在运行态目录，`KB_EVAL_REPORT_DIR` 可覆盖。"""
    env = str(os.getenv("KB_EVAL_REPORT_DIR", "")).strip()
    if env:
        return Path(env).expanduser()
    base = root if root is not None else _project_root()
    return base / "kb_store" / "eval"


def _project_root() -> Path:
    from src.shared.config_paths import resolve_project_root

    return resolve_project_root()


def make_kb_searcher(kb: Any, relevance_threshold: float | None = None) -> SearchFn:
    """把 KnowledgeBase.search 的 (filename, chunk, distance) 结果削成文件名序列。"""

    def _search(query: str, top_k: int) -> List[str]:
        results = kb.search(query, k=top_k, relevance_threshold=relevance_threshold)
        return [str(row[0]) for row in results if row]

    return _search


def run_evaluation(
    search_fn: SearchFn,
    cases: Sequence[GoldenCase],
    *,
    top_k: int = 10,
    ks: Sequence[int] = DEFAULT_KS,
    ndcg_k: int = DEFAULT_NDCG_K,
    dataset_path: str | Path | None = None,
    extra_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    跑完整套题集并汇总成报告字典。

    单题检索抛异常不会中断整轮：记成 0 分并留下 error 字段，
    否则一条脏数据就让几十分钟的跑分白跑。
    """
    if not cases:
        raise ValueError("题集为空，无法跑分")

    k_list = sorted({int(k) for k in ks if int(k) > 0})
    fetch_k = max([top_k, ndcg_k, *k_list]) if k_list else max(top_k, ndcg_k)

    case_rows: List[Dict[str, Any]] = []
    all_flags: List[List[bool]] = []
    latencies: List[float] = []
    started = time.perf_counter()

    for case in cases:
        t0 = time.perf_counter()
        error = ""
        try:
            ranked = list(search_fn(case.query, fetch_k))
        except Exception as exc:  # 单题失败不拖垮整轮
            ranked = []
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

        flags = matched_flags(ranked, case.positives)
        all_flags.append(flags)
        total_pos = len(case.positives)
        row: Dict[str, Any] = {
            "id": case.id,
            "query": case.query,
            "tags": list(case.tags),
            "positives": list(case.positives),
            "retrieved": ranked[:fetch_k],
            "hit": any(flags),
            "first_hit_rank": next((i for i, f in enumerate(flags, 1) if f), 0),
            "rr": reciprocal_rank(flags),
            f"ndcg@{ndcg_k}": ndcg_at_k(flags, total_pos, ndcg_k),
            "latency_ms": round(elapsed_ms, 3),
        }
        for k in k_list:
            row[f"recall@{k}"] = recall_at_k(flags, total_pos, k)
            row[f"precision@{k}"] = precision_at_k(flags, k)
        if error:
            row["error"] = error
        case_rows.append(row)

    total_seconds = time.perf_counter() - started

    summary: Dict[str, Any] = {
        "case_count": len(case_rows),
        "failed_count": sum(1 for row in case_rows if row.get("error")),
        "mrr": mean([float(row["rr"]) for row in case_rows]),
        f"ndcg@{ndcg_k}": mean([float(row[f"ndcg@{ndcg_k}"]) for row in case_rows]),
    }
    for k in k_list:
        summary[f"recall@{k}"] = mean([float(row[f"recall@{k}"]) for row in case_rows])
        summary[f"precision@{k}"] = mean(
            [float(row[f"precision@{k}"]) for row in case_rows]
        )
        summary[f"hit@{k}"] = mean([hit_at_k(flags, k) for flags in all_flags])
    summary["latency_ms"] = {
        "avg": round(mean(latencies), 3),
        "p50": round(percentile(latencies, 50), 3),
        "p95": round(percentile(latencies, 95), 3),
        "max": round(max(latencies), 3) if latencies else 0.0,
    }
    summary["total_seconds"] = round(total_seconds, 3)

    config: Dict[str, Any] = {
        "top_k": int(top_k),
        "fetch_k": int(fetch_k),
        "ks": k_list,
        "ndcg_k": int(ndcg_k),
    }
    if extra_config:
        config.update(extra_config)

    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "dataset": {
            "path": str(dataset_path) if dataset_path else "",
            "case_count": len(cases),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "config": config,
        "summary": summary,
        "cases": case_rows,
    }


def save_report(report: Dict[str, Any], out_path: str | Path | None = None) -> Path:
    """
    落盘报告。

    除了带时间戳的历史文件，还固定刷新一份 `latest.json`，
    这样 KB-11 看板只要认死一个路径就能拿到最近一次结果。
    """
    if out_path is not None:
        target = Path(out_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        report_dir = default_report_dir()
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = report_dir / f"report-{stamp}.json"

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    target.write_text(payload, encoding="utf-8")

    latest = target.parent / "latest.json"
    if latest != target:
        latest.write_text(payload, encoding="utf-8")
    return target
