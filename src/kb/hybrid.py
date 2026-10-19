"""
多路召回融合（RRF）。

向量 ANN 与 BM25 分数量纲不同，用 Reciprocal Rank Fusion 比直接加权更稳。
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple


def rrf_fuse(
    *ranked_lists: Sequence[Tuple[int, float]],
    top_n: int = 30,
    rrf_k: int = 60,
) -> List[Tuple[int, float]]:
    """
    多路 (doc_idx, score) 列表按排名做 RRF，返回融合后的 (doc_idx, rrf_score)。

    空列表会被跳过；全部为空则返回 []。
    """
    if top_n <= 0:
        return []
    k = max(1, int(rrf_k))
    fused: Dict[int, float] = {}
    for hits in ranked_lists:
        if not hits:
            continue
        for rank, (doc_idx, _score) in enumerate(hits):
            idx = int(doc_idx)
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    if not fused:
        return []
    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return [(idx, float(score)) for idx, score in ranked[: int(top_n)]]
