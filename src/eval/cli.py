"""
评测集命令行：一条命令跑分并落报告。

用法：
  python -m src.eval.cli --validate                     只校验题集格式，不动知识库
  python -m src.eval.cli                                用默认题集跑分（--top-k 省略则跟 KB-20 default_k）
  python -m src.eval.cli --dataset my.jsonl --top-k 5
  python -m src.eval.cli --min-recall5 0.85 --min-ndcg10 0.70   达不到质量线就退出码 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .dataset import DatasetError, default_dataset_path, load_dataset
from .runner import DEFAULT_KS, DEFAULT_NDCG_K, make_kb_searcher, run_evaluation, save_report


def _parse_ks(raw: str) -> List[int]:
    values = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    if not values:
        raise ValueError("--ks 至少要有一个正整数")
    return sorted({v for v in values if v > 0})


def _resolve_top_k(args_top_k: int | None, kb: Any, ks: List[int], ndcg_k: int) -> int:
    """
    未显式传 --top-k 时跟当前知识库 default_k（KB-20），
    并至少盖住指标所需的 max(ks, ndcg_k)，避免 Recall@10 / NDCG@10 测不满。
    """
    if args_top_k is not None:
        return max(1, int(args_top_k))
    try:
        default_k = max(1, int(getattr(kb, "default_k", 5) or 5))
    except Exception:
        default_k = 5
    metric_need = max([ndcg_k, *ks]) if ks else int(ndcg_k)
    return max(default_k, metric_need, 1)

def _print_summary(report: Dict[str, Any]) -> None:
    summary = report["summary"]
    config = report["config"]
    print("")
    print(f"题集：{report['dataset']['path'] or '(内存题集)'}")
    print(f"题目数：{summary['case_count']}    检索深度：{config['fetch_k']}")
    if summary.get("failed_count"):
        print(f"检索报错题数：{summary['failed_count']}（详见报告 error 字段）")
    print("")
    print("指标\t\t数值")
    print("-" * 32)
    for k in config["ks"]:
        print(f"Recall@{k}\t{summary[f'recall@{k}']:.4f}")
    ndcg_key = f"ndcg@{config['ndcg_k']}"
    print(f"NDCG@{config['ndcg_k']}\t\t{summary[ndcg_key]:.4f}")
    print(f"MRR\t\t{summary['mrr']:.4f}")
    if summary.get("negative_case_count"):
        rate = summary.get("false_recall_rate")
        print("-" * 32)
        print(
            f"反例题：{summary['negative_case_count']}    "
            f"误召回率：{(rate or 0.0):.4f}（证据门槛：{'开' if config.get('evidence_gate') else '关'}）"
        )
        if summary.get("false_recall_ids"):
            print(f"误召回题号：{'、'.join(summary['false_recall_ids'])}")
    latency = summary["latency_ms"]
    print("-" * 32)
    print(
        f"单题延迟 ms：avg {latency['avg']:.1f} / p50 {latency['p50']:.1f} / "
        f"p95 {latency['p95']:.1f} / max {latency['max']:.1f}"
    )
    print(f"总耗时：{summary['total_seconds']:.2f}s")


def _check_gates(report: Dict[str, Any], args: argparse.Namespace) -> bool:
    """质量线检查，给 CI 当闸门用；没设阈值就直接算通过。"""
    summary = report["summary"]
    passed = True
    if args.min_recall5 is not None:
        value = float(summary.get("recall@5", 0.0))
        ok = value >= args.min_recall5
        passed = passed and ok
        print(f"[{'PASS' if ok else 'FAIL'}] Recall@5 {value:.4f} >= {args.min_recall5}")
    if args.min_recall3 is not None:
        value = float(summary.get("recall@3", 0.0))
        ok = value >= args.min_recall3
        passed = passed and ok
        print(f"[{'PASS' if ok else 'FAIL'}] Recall@3 {value:.4f} >= {args.min_recall3}")
    if args.min_ndcg10 is not None:
        value = float(summary.get("ndcg@10", 0.0))
        ok = value >= args.min_ndcg10
        passed = passed and ok
        print(f"[{'PASS' if ok else 'FAIL'}] NDCG@10 {value:.4f} >= {args.min_ndcg10}")
    if args.max_latency_p95 is not None:
        value = float(summary.get("latency_ms", {}).get("p95", 0.0) or 0.0)
        ok = value <= args.max_latency_p95
        passed = passed and ok
        print(f"[{'PASS' if ok else 'FAIL'}] latency p95 {value:.1f}ms <= {args.max_latency_p95}")
    if args.max_false_recall is not None:
        rate = summary.get("false_recall_rate")
        if rate is None:
            print("[SKIP] 题集没有反例题，跳过误召回率检查")
        else:
            ok = float(rate) <= args.max_false_recall
            passed = passed and ok
            print(f"[{'PASS' if ok else 'FAIL'}] 误召回率 {float(rate):.4f} <= {args.max_false_recall}")
    return passed


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WIKI KB 检索评测集跑分（KB-10）")
    parser.add_argument("--dataset", default="", help="题集 JSONL 路径；默认用 conf/eval/golden-default.jsonl")
    parser.add_argument("--validate", action="store_true", help="只校验题集格式，不加载知识库")
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="检索返回条数；省略则使用知识库 default_k，并至少覆盖 --ks/--ndcg-k",
    )
    parser.add_argument("--ks", default=",".join(str(k) for k in DEFAULT_KS), help="Recall/Precision 的 k 列表")
    parser.add_argument("--ndcg-k", type=int, default=DEFAULT_NDCG_K, help="NDCG 的 k")
    parser.add_argument("--threshold", type=float, default=None, help="检索相关性阈值；不填表示不过滤")
    parser.add_argument("--persist-dir", default=None, help="知识库持久化目录覆盖")
    parser.add_argument("--dimension", type=int, default=None, help="向量维度覆盖")
    parser.add_argument("--out", default="", help="报告输出路径；不填则落到 kb_store/eval/")
    parser.add_argument("--no-save", action="store_true", help="只打印结果，不落报告文件")
    parser.add_argument("--json", action="store_true", help="把完整报告 JSON 打到标准输出")
    parser.add_argument("--min-recall5", type=float, default=None, help="质量线：Recall@5 下限，不达标退出码 1")
    parser.add_argument("--min-ndcg10", type=float, default=None, help="质量线：NDCG@10 下限，不达标退出码 1")
    parser.add_argument(
        "--min-recall3",
        type=float,
        default=None,
        help="质量线：Recall@3 下限（KB-01），不达标退出码 1",
    )
    parser.add_argument(
        "--max-latency-p95",
        type=float,
        default=None,
        help="质量线：单题检索延迟 p95 上限（毫秒），不达标退出码 1",
    )
    parser.add_argument(
        "--max-false-recall",
        type=float,
        default=None,
        help="质量线：反例题误召回率上限（0～1），不达标退出码 1",
    )
    parser.add_argument(
        "--no-evidence-gate",
        action="store_true",
        help="跑分时不走证据门槛，只看裸检索结果（对比门槛前后用）",
    )
    parser.add_argument(
        "--hybrid",
        choices=("on", "off", "default"),
        default="default",
        help="覆盖运行时 hybrid_enabled：on/off；default 表示沿用配置",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="临时将 rerank_weight 置 0，用于测召回融合延迟（不含交叉编码器重排）",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="计时前预热检索次数（默认 3，排除冷启动；0 关闭）",
    )
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset) if args.dataset else default_dataset_path()
    try:
        cases = load_dataset(dataset_path)
    except (DatasetError, FileNotFoundError) as exc:
        print(f"[FAIL] 题集加载失败：{exc}", file=sys.stderr)
        return 2

    if args.validate:
        tags = sorted({t for case in cases for t in case.tags})
        print(f"[OK] 题集可用：{dataset_path}")
        print(f"     题目数：{len(cases)}")
        print(f"     标签：{'、'.join(tags) if tags else '(无)'}")
        return 0

    try:
        ks = _parse_ks(args.ks)
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    # 延迟导入：--validate 路径不该被模型依赖拖住
    try:
        from src.knowledge_base import KnowledgeBase
    except ImportError as exc:
        print(f"[FAIL] 无法加载知识库：{exc}", file=sys.stderr)
        return 2

    kb = KnowledgeBase(dimension=args.dimension, persist_dir=args.persist_dir)
    if args.hybrid == "on":
        kb.hybrid_enabled = True
    elif args.hybrid == "off":
        kb.hybrid_enabled = False
    if args.no_rerank:
        kb.rerank_weight = 0.0
        kb.embed_weight = 1.0
    top_k = _resolve_top_k(args.top_k, kb, ks, int(args.ndcg_k))
    report = run_evaluation(
        make_kb_searcher(
            kb,
            relevance_threshold=args.threshold,
            apply_evidence_gate=not args.no_evidence_gate,
        ),
        cases,
        top_k=top_k,
        ks=ks,
        ndcg_k=int(args.ndcg_k),
        dataset_path=dataset_path,
        warmup=int(args.warmup),
        extra_config={
            "relevance_threshold": args.threshold,
            "persist_dir": args.persist_dir or "",
            "top_k_source": "cli" if args.top_k is not None else "kb_default",
            "default_k": int(getattr(kb, "default_k", 0) or 0),
            "chunk_size": int(getattr(kb, "chunk_size", 0) or 0),
            "chunk_overlap": int(getattr(kb, "chunk_overlap", 0) or 0),
            "max_search_results": int(getattr(kb, "max_search_results", 0) or 0),
            "hybrid_enabled": bool(getattr(kb, "hybrid_enabled", True)),
            "rrf_k": int(getattr(kb, "rrf_k", 60) or 60),
            "max_rerank_candidates": int(getattr(kb, "max_rerank_candidates", 8) or 8),
            "rerank_weight": float(getattr(kb, "rerank_weight", 0.0) or 0.0),
            "no_rerank": bool(args.no_rerank),
            "max_rerank_chunks_per_file": int(getattr(kb, "max_rerank_chunks_per_file", 3) or 3),
            "evidence_policy": (
                kb.evidence_policy.to_dict() if hasattr(kb, "evidence_policy") else None
            ),
            "embedding_consistency": (
                kb.embedding_consistency() if hasattr(kb, "embedding_consistency") else None
            ),
        },
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_summary(report)

    if not args.no_save:
        saved = save_report(report, args.out or None)
        print(f"报告已写入：{saved}")

    return 0 if _check_gates(report, args) else 1


if __name__ == "__main__":
    sys.exit(main())
