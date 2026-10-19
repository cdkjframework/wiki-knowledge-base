"""
轻量 Okapi BM25 索引（纯标准库，无 jieba / rank_bm25 依赖）。

面向中英混合语料：英文按词；中文按字 + 双字（bigram），够用做字面召回通道。
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from .query_terms import tokenize_query

_LATIN_WORD = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> List[str]:
    """把一段文本切成 BM25 词元。"""
    raw = (text or "").strip().lower()
    if not raw:
        return []
    tokens: List[str] = []
    tokens.extend(_LATIN_WORD.findall(raw))
    cjk = _CJK_CHAR.findall(raw)
    if cjk:
        tokens.extend(cjk)
        if len(cjk) >= 2:
            tokens.extend(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
    return tokens


class Bm25Index:
    """
    内存 BM25。文档列表与 chunk 下标一一对应；空文档保留占位，搜索时自然得低分。
    """

    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = float(k1)
        self.b = float(b)
        self._doc_len: List[int] = []
        self._tf: List[Counter[str]] = []
        self._df: Dict[str, int] = defaultdict(int)
        self._avgdl = 0.0
        self._n = 0

    def build(self, documents: Sequence[str]) -> None:
        self._doc_len = []
        self._tf = []
        self._df = defaultdict(int)
        self._n = 0
        total_len = 0
        for doc in documents:
            toks = tokenize(doc)
            tf = Counter(toks)
            self._tf.append(tf)
            length = sum(tf.values())
            self._doc_len.append(length)
            total_len += length
            for term in tf:
                self._df[term] += 1
            self._n += 1
        self._avgdl = (total_len / self._n) if self._n else 0.0

    def _idf(self, term: str) -> float:
        # 经典 BM25 IDF，对未见词返回 0
        df = self._df.get(term, 0)
        if df <= 0 or self._n <= 0:
            return 0.0
        return math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        top_n: int = 10,
        *,
        extra_generic: Iterable[str] | None = None,
    ) -> List[Tuple[int, float]]:
        """
        返回 (doc_index, score) 按分数降序。

        查询端走 tokenize_query（剥泛词、实体查询丢中文单字），索引端词元不变。
        """
        return self.search_terms(tokenize_query(query, extra_generic=extra_generic), top_n=top_n)

    def search_terms(self, q_terms: Sequence[str], top_n: int = 10) -> List[Tuple[int, float]]:
        """直接按给定查询词元打分；词元为空返回空，交给向量通道兜底。"""
        if self._n <= 0 or top_n <= 0:
            return []
        if not q_terms:
            return []
        # 查询词去重但保留 IDF 权重（重复词不再叠加）
        unique_terms = list(dict.fromkeys(q_terms))
        scores = [0.0] * self._n
        avgdl = self._avgdl if self._avgdl > 0 else 1.0
        k1 = self.k1
        b = self.b
        for term in unique_terms:
            idf = self._idf(term)
            if idf <= 0:
                continue
            for i, tf in enumerate(self._tf):
                freq = tf.get(term, 0)
                if freq <= 0:
                    continue
                dl = self._doc_len[i] or 0
                denom = freq + k1 * (1.0 - b + b * dl / avgdl)
                scores[i] += idf * (freq * (k1 + 1.0)) / denom

        ranked = [(i, s) for i, s in enumerate(scores) if s > 0]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[: int(top_n)]


def build_bm25(documents: Iterable[str], *, k1: float = 1.5, b: float = 0.75) -> Bm25Index:
    idx = Bm25Index(k1=k1, b=b)
    idx.build(list(documents))
    return idx
