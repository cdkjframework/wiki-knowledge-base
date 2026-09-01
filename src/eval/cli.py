"""
评测集命令行：一条命令跑分并落报告。

用法：
  python -m src.eval.cli --validate                     只校验题集格式，不动知识库
  python -m src.eval.cli                                用默认题集跑分并落报告
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
    if args.min_ndcg10 is not None:
        value = float(summary.get("ndcg@10", 0.0))
        ok = value >= args.min_ndcg10
        passed = passed and ok
        print(f"[{'PASS' if ok else 'FAIL'}] NDCG@10 {value:.4f} >= {args.min_ndcg10}")
    return passed


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WIKI KB 检索评测集跑分（KB-10）")
    parser.add_argument("--dataset", default="", help="题集 JSONL 路径；默认用 conf/eval/golden-default.jsonl")
    parser.add_argument("--validate", action="store_true", help="只校验题集格式，不加载知识库")
    parser.add_argument("--top-k", type=int, default=10, help="检索返回条数")
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
    report = run_evaluation(
        make_kb_searcher(kb, relevance_threshold=args.threshold),
        cases,
        top_k=int(args.top_k),
        ks=ks,
        ndcg_k=int(args.ndcg_k),
        dataset_path=dataset_path,
        extra_config={
            "relevance_threshold": args.threshold,
            "persist_dir": args.persist_dir or "",
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
