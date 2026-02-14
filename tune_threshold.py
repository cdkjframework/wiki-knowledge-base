"""
Sweep relevance_threshold values and evaluate retrieval quality.

Input dataset format (JSONL, UTF-8), one sample per line:
{"query": "...", "positive_filenames": ["doc1.pdf", "doc2.docx"]}

Minimal accepted aliases for positives:
- positive_filenames (list[str])
- expected_filenames (list[str])
- expected_filename (str)
- filename (str)
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from knowledge_base import KnowledgeBase


@dataclass
class EvalItem:
    query: str
    positives: Set[str]


def parse_thresholds(raw: str) -> List[float]:
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(float(part))
    if not values:
        raise ValueError("No valid thresholds provided")
    return sorted(set(values))


def parse_eval_item(line: str, lineno: int) -> EvalItem:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON at line {lineno}: {exc}") from exc

    query = (obj.get("query") or "").strip()
    if not query:
        raise ValueError(f"Missing query at line {lineno}")

    positives = set()

    list_fields = ["positive_filenames", "expected_filenames"]
    for field in list_fields:
        value = obj.get(field)
        if not isinstance(value, list):
            continue
        positives.update(str(x).strip() for x in value if str(x).strip())

    scalar_fields = ["expected_filename", "filename"]
    for field in scalar_fields:
        value = obj.get(field)
        if isinstance(value, str) and value.strip():
            positives.add(value.strip())

    if not positives:
        raise ValueError(
            f"Missing positives at line {lineno}; provide one of "
            "positive_filenames/expected_filenames/expected_filename/filename"
        )

    return EvalItem(query=query, positives=positives)


def load_dataset(path: str) -> List[EvalItem]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")

    items = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            items.append(parse_eval_item(line, lineno))

    if not items:
        raise ValueError("Dataset is empty")
    return items


def reciprocal_rank(
    results: Sequence[Tuple[str, str, float]], positives: Set[str]
) -> float:
    for rank, (filename, _, _) in enumerate(results, start=1):
        if filename in positives:
            return 1.0 / rank
    return 0.0


def hit_at_k(results: Sequence[Tuple[str, str, float]], positives: Set[str]) -> float:
    for filename, _, _ in results:
        if filename in positives:
            return 1.0
    return 0.0


def evaluate(
    kb: KnowledgeBase, dataset: Iterable[EvalItem], threshold: float, k: int
) -> Tuple[float, float, float]:
    hit_sum = 0.0
    mrr_sum = 0.0
    results_count_sum = 0
    total = 0

    for item in dataset:
        results = kb.search(item.query, k=k, relevance_threshold=threshold)
        hit_sum += hit_at_k(results, item.positives)
        mrr_sum += reciprocal_rank(results, item.positives)
        results_count_sum += len(results)
        total += 1

    return hit_sum / total, mrr_sum / total, results_count_sum / total


def main() -> None:
    parser = argparse.ArgumentParser(description="Threshold sweep for KB retrieval.")
    parser.add_argument("--dataset", required=True, help="Path to JSONL eval dataset.")
    parser.add_argument(
        "--thresholds",
        default="0.8,1.0,1.2,1.4,1.6",
        help="Comma-separated threshold list.",
    )
    parser.add_argument("--k", type=int, default=3, help="Top-k for retrieval.")
    parser.add_argument(
        "--persist-dir",
        default=None,
        help="Optional KB persist directory override.",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=None,
        help="Optional KB dimension override.",
    )
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    thresholds = parse_thresholds(args.thresholds)

    kb = KnowledgeBase(dimension=args.dimension, persist_dir=args.persist_dir)

    print(f"[INFO] Loaded eval samples: {len(dataset)}")
    print(f"[INFO] Threshold candidates: {thresholds}")
    print(f"[INFO] Retrieval top-k: {args.k}")
    print("")
    print("threshold\thit@k\tmrr\tavg_results")

    best_threshold = None
    best_score = -1.0
    rows = []
    for threshold in thresholds:
        hit_k, mrr, avg_results = evaluate(kb, dataset, threshold, args.k)
        rows.append((threshold, hit_k, mrr, avg_results))
        print(f"{threshold:.4f}\t{hit_k:.4f}\t{mrr:.4f}\t{avg_results:.2f}")

        score = hit_k * 1000.0 + mrr * 10.0 - avg_results
        if score > best_score:
            best_score = score
            best_threshold = threshold

    print("")
    print(f"[RECOMMENDED] relevance_threshold={best_threshold:.4f}")
    print(
        "[DETAIL] Selection rule: maximize hit@k, then mrr, then smaller avg_results."
    )


if __name__ == "__main__":
    main()

