"""
KB-10 评测集：用固定题集给检索质量打分。

对外只暴露「加载题集 → 跑分 → 落报告」三件事，指标实现保持零三方依赖，
这样单测不用加载模型也能验证算法本身。
"""

from __future__ import annotations

from .dataset import (
    GoldenCase,
    default_dataset_path,
    load_dataset,
    parse_case,
)
from .metrics import (
    hit_at_k,
    matched_flags,
    mean,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from .runner import (
    REPORT_SCHEMA,
    default_report_dir,
    make_kb_searcher,
    run_evaluation,
    save_report,
)

__all__ = [
    "GoldenCase",
    "default_dataset_path",
    "load_dataset",
    "parse_case",
    "hit_at_k",
    "matched_flags",
    "mean",
    "ndcg_at_k",
    "percentile",
    "recall_at_k",
    "reciprocal_rank",
    "REPORT_SCHEMA",
    "default_report_dir",
    "make_kb_searcher",
    "run_evaluation",
    "save_report",
]
