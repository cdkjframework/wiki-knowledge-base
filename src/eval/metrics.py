"""
检索质量指标：Recall@k / NDCG@k / MRR / Hit@k 与延迟分位。

只用标准库，方便单测直接验证算法，不必真的起知识库。
所有指标都基于「命中标记序列」计算：先把检索结果和标准答案对齐成
[True, False, ...]，再由各指标各自解读，避免每个指标重复写匹配逻辑。
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Set


def normalize_doc_id(value: str) -> str:
    """把文档标识归一化成小写正斜杠路径，避免大小写和分隔符导致漏匹配。"""
    return str(value or "").strip().replace("\\", "/").lower()


def _is_match(doc: str, positives: Set[str]) -> bool:
    """题集里常只写文件名而检索返回带目录的路径，所以允许后缀式匹配。"""
    if not doc:
        return False
    if doc in positives:
        return True
    for pos in positives:
        if not pos:
            continue
        if doc.endswith("/" + pos) or pos.endswith("/" + doc):
            return True
    return False


def matched_flags(ranked: Sequence[str], positives: Iterable[str]) -> List[bool]:
    """
    把检索结果按名次标成是否命中。

    同一文档重复出现只算第一次，防止一篇正确文档占满前几名把 Recall 刷高。
    """
    pos_set = {normalize_doc_id(p) for p in positives if str(p).strip()}
    seen: Set[str] = set()
    flags: List[bool] = []
    for item in ranked:
        doc = normalize_doc_id(item)
        hit = _is_match(doc, pos_set) and doc not in seen
        if hit:
            seen.add(doc)
        flags.append(hit)
    return flags


def recall_at_k(flags: Sequence[bool], total_positives: int, k: int) -> float:
    """前 k 名里找回了多少标准答案。"""
    if total_positives <= 0 or k <= 0:
        return 0.0
    hits = sum(1 for flag in flags[:k] if flag)
    return min(1.0, hits / float(total_positives))


def precision_at_k(flags: Sequence[bool], k: int) -> float:
    """前 k 名里有多少是对的。"""
    if k <= 0:
        return 0.0
    window = flags[:k]
    if not window:
        return 0.0
    return sum(1 for flag in window if flag) / float(len(window))


def hit_at_k(flags: Sequence[bool], k: int) -> float:
    """前 k 名里只要命中一条就算 1，用来看「起码找着了没」。"""
    return 1.0 if any(flags[:k]) else 0.0


def reciprocal_rank(flags: Sequence[bool]) -> float:
    """第一条正确结果排第几名的倒数，越靠前越接近 1。"""
    for idx, flag in enumerate(flags, start=1):
        if flag:
            return 1.0 / idx
    return 0.0


def ndcg_at_k(flags: Sequence[bool], total_positives: int, k: int) -> float:
    """
    二值相关性的 NDCG@k。

    理想序列是「所有正确答案都排在最前面」，但正确答案多于 k 时也只能占满 k 个位置，
    所以 IDCG 取 min(正确答案数, k)。
    """
    if total_positives <= 0 or k <= 0:
        return 0.0
    dcg = 0.0
    for idx, flag in enumerate(flags[:k]):
        if flag:
            dcg += 1.0 / math.log2(idx + 2)
    ideal_hits = min(total_positives, k)
    idcg = sum(1.0 / math.log2(idx + 2) for idx in range(ideal_hits))
    if idcg <= 0:
        return 0.0
    return dcg / idcg


def mean(values: Sequence[float]) -> float:
    """空列表返回 0，省得调用方到处判空。"""
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def percentile(values: Sequence[float], pct: float) -> float:
    """
    线性插值分位数，用于延迟 p50 / p95。

    不引入 numpy，是为了让评测内核在最小依赖环境（比如 CI 冒烟）里也能跑。
    """
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    ratio = max(0.0, min(100.0, float(pct))) / 100.0
    pos = ratio * (len(ordered) - 1)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)
