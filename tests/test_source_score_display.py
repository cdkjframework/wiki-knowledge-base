"""来源分数展示：相对排序分 + 向量/重排拆分。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any


class _FakeKb:
    def __init__(self, details: list[dict[str, Any]] | None = None) -> None:
        self._last_search_details = list(details or [])


class SourceResultItemsTests(unittest.TestCase):
    def _api(self, details: list[dict[str, Any]]) -> Any:
        from src.api.http_server import KnowledgeBaseApi

        api = KnowledgeBaseApi.__new__(KnowledgeBaseApi)
        api.kb = _FakeKb(details)
        return api

    def test_relative_score_tops_at_one_and_keeps_breakdown(self) -> None:
        api = self._api(
            [
                {
                    "filename": "a.md",
                    "final_similarity": 0.66,
                    "embed_similarity": 0.5,
                    "rerank_similarity": 0.75,
                },
                {
                    "filename": "b.md",
                    "final_similarity": 0.33,
                    "embed_similarity": 0.4,
                    "rerank_similarity": 0.3,
                },
            ]
        )
        # distance 只是占位；合成分以 _last_search_details 为准
        raw = [
            ("a.md", "关于 WIKI", 0.5),
            ("b.md", "其它文档", 2.0),
        ]
        ranked, items = api._build_source_result_items(raw, min_similarity=0.0)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(items[0]["rank"], 1)
        self.assertEqual(items[0]["relative_similarity"], 1.0)
        self.assertEqual(items[0]["score_label"], "一般")
        self.assertEqual(items[0]["embed_similarity"], 0.5)
        self.assertEqual(items[0]["rerank_similarity"], 0.75)
        self.assertEqual(items[1]["rank"], 2)
        self.assertAlmostEqual(items[1]["relative_similarity"], 0.5, places=3)
        # 明细读完应清空，避免串请求
        self.assertEqual(api.kb._last_search_details, [])

    def test_channel_scores_pass_through(self) -> None:
        api = self._api(
            [
                {
                    "filename": "bm25only.md",
                    "final_similarity": 0.55,
                    "vector_similarity": None,
                    "embed_similarity": None,
                    "bm25_score": 3.2,
                    "rerank_raw": 0.4,
                    "rerank_similarity": 0.6,
                    "rerank_status": "ok",
                    "channels": ["bm25"],
                }
            ]
        )
        _, items = api._build_source_result_items([("bm25only.md", "片段", 0.8)], min_similarity=0.0)
        item = items[0]
        # 只被 BM25 捞到的候选不能再显示出「向量 1.00」
        self.assertIsNone(item["vector_similarity"])
        self.assertIsNone(item["embed_similarity"])
        self.assertEqual(item["bm25_score"], 3.2)
        self.assertEqual(item["rerank_similarity"], 0.6)
        self.assertEqual(item["rerank_status"], "ok")
        self.assertEqual(item["channels"], ["bm25"])

    def test_score_label_bands(self) -> None:
        from src.api.http_server import KnowledgeBaseApi

        self.assertEqual(KnowledgeBaseApi._score_strength_label(0.9), "较强")
        self.assertEqual(KnowledgeBaseApi._score_strength_label(0.66), "一般")
        self.assertEqual(KnowledgeBaseApi._score_strength_label(0.4), "较弱")

    def test_min_similarity_still_filters(self) -> None:
        api = self._api(
            [
                {
                    "filename": "keep.md",
                    "final_similarity": 0.7,
                    "embed_similarity": 0.7,
                    "rerank_similarity": None,
                },
                {
                    "filename": "drop.md",
                    "final_similarity": 0.4,
                    "embed_similarity": 0.4,
                    "rerank_similarity": None,
                },
            ]
        )
        raw = [
            ("keep.md", "保留", 0.43),
            ("drop.md", "丢掉", 1.5),
        ]
        _, items = api._build_source_result_items(raw, min_similarity=0.6)
        self.assertEqual([x["filename"] for x in items], ["keep.md"])


if __name__ == "__main__":
    unittest.main()
