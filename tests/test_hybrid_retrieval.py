"""KB-01：BM25 索引、RRF 融合与混合检索降级。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import List, Tuple
from unittest.mock import patch


class Bm25IndexTests(unittest.TestCase):
    def test_literal_hit_ranks_higher(self) -> None:
        from src.kb.bm25_index import build_bm25

        docs = [
            "今天天气不错，适合出门散步。",
            "WIKI 本地知识库支持混合检索与固定长度分片。",
            "完全无关的一句闲聊。",
        ]
        idx = build_bm25(docs)
        hits = idx.search("混合检索 知识库", top_n=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0][0], 1)

    def test_empty_query(self) -> None:
        from src.kb.bm25_index import build_bm25

        idx = build_bm25(["hello world"])
        self.assertEqual(idx.search("", top_n=5), [])


class RrfFuseTests(unittest.TestCase):
    def test_fuse_prefers_shared_hits(self) -> None:
        from src.kb.hybrid import rrf_fuse

        a = [(0, 0.9), (1, 0.8), (2, 0.1)]
        b = [(1, 5.0), (3, 4.0), (0, 1.0)]
        fused = rrf_fuse(a, b, top_n=4, rrf_k=60)
        self.assertEqual(fused[0][0], 1)
        ids = [i for i, _ in fused]
        self.assertIn(0, ids)
        self.assertIn(3, ids)

    def test_empty_lists(self) -> None:
        from src.kb.hybrid import rrf_fuse

        self.assertEqual(rrf_fuse([], [], top_n=5), [])
        only = rrf_fuse([(2, 1.0)], [], top_n=5)
        self.assertEqual(only[0][0], 2)


class HybridSettingsTests(unittest.TestCase):
    def test_normalize_hybrid_fields(self) -> None:
        from src.kb.retrieval_settings import (
            apply_settings_to_config,
            apply_settings_to_runtime,
            normalize_settings,
            snapshot_from_runtime,
        )

        settings = normalize_settings(
            {"hybrid_enabled": False, "rrf_k": 40},
            current={
                "default_k": 5,
                "max_search_results": 10,
                "min_source_similarity": 0.0,
                "chunk_size": 800,
                "chunk_overlap": 120,
                "hybrid_enabled": True,
                "rrf_k": 60,
            },
        )
        self.assertFalse(settings["hybrid_enabled"])
        self.assertEqual(settings["rrf_k"], 40)

        cfg: dict = {}
        apply_settings_to_config(cfg, settings)
        self.assertFalse(cfg["search"]["hybrid_enabled"])
        self.assertEqual(cfg["knowledge_base"]["retrieval"]["rrf_k"], 40)

        kb = SimpleNamespace(
            default_k=5,
            max_search_results=10,
            chunk_size=800,
            chunk_overlap=120,
            hybrid_enabled=True,
            rrf_k=60,
        )
        search_cfg: dict = {}
        apply_settings_to_runtime(kb, search_cfg, settings)
        snap = snapshot_from_runtime(kb, search_cfg)
        self.assertFalse(snap["hybrid_enabled"])
        self.assertEqual(snap["rrf_k"], 40)
        self.assertIn("hybrid", snap["notes"])

    def test_reject_bad_rrf(self) -> None:
        from src.kb.retrieval_settings import normalize_settings

        with self.assertRaises(ValueError):
            normalize_settings({"rrf_k": 0})


class HybridSearchDegradeTests(unittest.TestCase):
    """不加载真模型：打桩向量/重排，验证 BM25 通道与降级。"""

    def _make_kb(self):
        from src.knowledge_base import KnowledgeBase, _Chunk
        from src.kb.bm25_index import build_bm25

        kb = object.__new__(KnowledgeBase)
        kb._chunks = [
            _Chunk(filename="a.md", text="完全无关的闲聊内容。"),
            _Chunk(filename="b.md", text="WIKI 混合检索支持 BM25 与向量双通道召回。"),
            _Chunk(filename="c.md", text="另一段天气与散步的描述。"),
        ]
        kb._bm25 = build_bm25([c.text for c in kb._chunks])
        kb.default_k = 3
        kb.max_search_results = 10
        kb.candidate_multiplier = 2
        kb.min_candidates = 3
        kb.embed_weight = 0.35
        kb.rerank_weight = 0.0  # 跳过真实 rerank
        kb.hybrid_enabled = True
        kb.rrf_k = 60
        kb.max_rerank_candidates = 8
        kb._index = SimpleNamespace(ntotal=3)
        return kb

    def test_bm25_only_when_vector_empty(self) -> None:
        kb = self._make_kb()

        def fake_embed(_texts):  # noqa: ANN001
            import numpy as np

            return np.zeros((0, 8), dtype=np.float32)

        with patch.object(kb, "_embed_texts", side_effect=fake_embed):
            results = kb.search("BM25 混合检索", k=2)
        self.assertTrue(results)
        self.assertEqual(results[0][0], "b.md")

    def test_vector_only_when_hybrid_off(self) -> None:
        kb = self._make_kb()
        kb.hybrid_enabled = False

        def fake_embed(_texts):  # noqa: ANN001
            import numpy as np

            return np.ones((1, 8), dtype=np.float32)

        def fake_candidate(_q, top_n=3):  # noqa: ANN001
            return [(0, 0.99), (2, 0.5)][:top_n]

        with (
            patch.object(kb, "_embed_texts", side_effect=fake_embed),
            patch.object(kb, "_candidate_search", side_effect=fake_candidate),
            patch.object(kb, "_bm25_search", return_value=[(1, 9.0)]) as bm25_mock,
        ):
            results = kb.search("任意查询", k=2)
            bm25_mock.assert_not_called()
        self.assertEqual(results[0][0], "a.md")

    def test_rrf_merges_channels(self) -> None:
        kb = self._make_kb()

        def fake_embed(_texts):  # noqa: ANN001
            import numpy as np

            return np.ones((1, 8), dtype=np.float32)

        def fake_candidate(_q, top_n=3):  # noqa: ANN001
            return [(0, 0.9), (2, 0.8)][:top_n]

        with (
            patch.object(kb, "_embed_texts", side_effect=fake_embed),
            patch.object(kb, "_candidate_search", side_effect=fake_candidate),
        ):
            results = kb.search("BM25 混合检索", k=3)
        filenames = [r[0] for r in results]
        # BM25 强命中 b.md，应出现在融合结果里
        self.assertIn("b.md", filenames)


class Bm25QueryTermTests(unittest.TestCase):
    """PMP内容 误召回：泛词与中文单字不能替实体去捞无关文档。"""

    def test_generic_word_alone_does_not_recall(self) -> None:
        from src.kb.bm25_index import build_bm25

        docs = [
            "本手册内容包括电子凭证开立与作废。",
            "系统内容管理模块说明。",
        ]
        idx = build_bm25(docs)
        self.assertEqual(idx.search("PMP内容", top_n=5), [])

    def test_entity_still_hits_when_present(self) -> None:
        from src.kb.bm25_index import build_bm25

        docs = ["电子凭证手册内容", "PMP 认证考试说明与报名流程"]
        idx = build_bm25(docs)
        hits = idx.search("PMP内容", top_n=5)
        self.assertEqual([i for i, _ in hits], [1])

    def test_plain_chinese_recall_unchanged(self) -> None:
        from src.kb.bm25_index import build_bm25

        docs = ["今天天气不错", "报销流程：先提交申请再审批", "无关闲聊"]
        idx = build_bm25(docs)
        hits = idx.search("报销流程怎么走", top_n=3)
        self.assertEqual(hits[0][0], 1)


def _stub_kb(texts: List[Tuple[str, str]]):
    """不加载模型的 KnowledgeBase 壳子；检索通道都靠打桩。"""
    import numpy as np

    from src.kb.bm25_index import build_bm25
    from src.kb.evidence_gate import EvidencePolicy
    from src.knowledge_base import KnowledgeBase, _Chunk

    kb = object.__new__(KnowledgeBase)
    kb._chunks = [_Chunk(filename=fn, text=tx) for fn, tx in texts]
    kb._bm25 = build_bm25([c.text for c in kb._chunks])
    kb.default_k = 5
    kb.max_search_results = 10
    kb.candidate_multiplier = 2
    kb.min_candidates = len(texts)
    kb.embed_weight = 0.35
    kb.rerank_weight = 0.65
    kb.hybrid_enabled = True
    kb.rrf_k = 60
    kb.max_rerank_candidates = 8
    kb.max_rerank_chunks_per_file = 3
    kb.evidence_policy = EvidencePolicy()
    kb._index = SimpleNamespace(ntotal=len(texts))
    kb._embeddings = np.zeros((0, 4), dtype=np.float32)
    kb._index_embedding_model = None
    kb.embedding_model_name = "Qwen/Qwen3-Embedding-0.6B"
    return kb


class HybridScoreSeparationTests(unittest.TestCase):
    def test_fusion_keeps_channel_scores_apart(self) -> None:
        kb = _stub_kb([("a.md", "x"), ("b.md", "y"), ("c.md", "z")])
        cands, channel = kb._fuse_hybrid_candidates(
            [(0, 0.9), (2, 0.4)], [(1, 7.5), (0, 3.0)], top_n=5
        )
        self.assertEqual(channel, "hybrid_rrf")
        by_idx = {c["idx"]: c for c in cands}
        self.assertEqual(by_idx[0]["channels"], ["vector", "bm25"])
        self.assertEqual(by_idx[0]["vector_similarity"], 0.9)
        self.assertEqual(by_idx[1]["channels"], ["bm25"])
        # BM25 独有候选不再拿「BM25/最高分=1.0」冒充向量分
        self.assertIsNone(by_idx[1]["vector_similarity"])
        self.assertEqual(by_idx[1]["bm25_score"], 7.5)

    def test_bm25_only_candidate_has_no_fake_vector_score(self) -> None:
        import numpy as np

        kb = _stub_kb(
            [("a.md", "完全无关的闲聊"), ("b.md", "WIKI 混合检索支持 BM25 召回"), ("c.md", "天气")]
        )
        kb.rerank_weight = 0.0
        with (
            patch.object(kb, "_embed_texts", return_value=np.ones((1, 4), dtype=np.float32)),
            patch.object(kb, "_candidate_search", return_value=[(0, 0.7)]),
        ):
            kb.search("BM25 混合检索", k=3)
        details = {d["filename"]: d for d in kb._last_search_details}
        self.assertIn("b.md", details)
        self.assertIsNone(details["b.md"]["vector_similarity"])
        self.assertIsNone(details["b.md"]["embed_similarity"])
        self.assertEqual(details["b.md"]["channels"], ["bm25"])
        self.assertEqual(details["a.md"]["vector_similarity"], 0.7)
        self.assertEqual(details["a.md"]["rerank_status"], "disabled")

    def test_verified_model_fills_cosine_for_bm25_only(self) -> None:
        import numpy as np

        kb = _stub_kb([("a.md", "闲聊"), ("b.md", "混合检索 BM25")])
        kb.rerank_weight = 0.0
        kb._embeddings = np.array([[1, 0, 0, 0], [0.6, 0.8, 0, 0]], dtype=np.float32)
        kb._index_embedding_model = "Qwen/Qwen3-Embedding-0.6B"
        kb.embedding_model_name = "text-embedding-qwen3-embedding-0.6b"
        self.assertEqual(kb.embedding_consistency(), "verified")
        q = np.array([[0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        with (
            patch.object(kb, "_embed_texts", return_value=q),
            patch.object(kb, "_candidate_search", return_value=[(0, 0.1)]),
        ):
            kb.search("混合检索 BM25", k=2)
        details = {d["filename"]: d for d in kb._last_search_details}
        self.assertAlmostEqual(details["b.md"]["vector_similarity"], 0.8, places=3)
        self.assertEqual(details["b.md"]["vector_score_source"], "computed")

    def test_unverified_model_skips_cosine(self) -> None:
        import numpy as np

        kb = _stub_kb([("a.md", "闲聊"), ("b.md", "混合检索 BM25")])
        kb.rerank_weight = 0.0
        kb._embeddings = np.array([[1, 0, 0, 0], [0.6, 0.8, 0, 0]], dtype=np.float32)
        kb._index_embedding_model = "BAAI/bge-m3"
        self.assertEqual(kb.embedding_consistency(), "unverified")
        with (
            patch.object(kb, "_embed_texts", return_value=np.ones((1, 4), dtype=np.float32)),
            patch.object(kb, "_candidate_search", return_value=[(0, 0.1)]),
        ):
            kb.search("混合检索 BM25", k=2)
        details = {d["filename"]: d for d in kb._last_search_details}
        self.assertIsNone(details["b.md"]["vector_similarity"])

    def test_rerank_failure_leaves_no_fake_scores(self) -> None:
        import numpy as np

        kb = _stub_kb([("a.md", "闲聊"), ("b.md", "混合检索 BM25")])
        with (
            patch.object(kb, "_embed_texts", return_value=np.ones((1, 4), dtype=np.float32)),
            patch.object(kb, "_candidate_search", return_value=[(0, 0.6)]),
            patch.object(kb, "_rerank_scores", side_effect=RuntimeError("重排挂了")),
        ):
            kb.search("混合检索 BM25", k=2)
        details = {d["filename"]: d for d in kb._last_search_details}
        for detail in details.values():
            self.assertEqual(detail["rerank_status"], "failed")
            self.assertIsNone(detail["rerank_similarity"])
        # 只剩向量证据时合成分就是向量分；BM25 独有候选没有任何语义证据，合成分为 0
        self.assertAlmostEqual(details["a.md"]["final_similarity"], 0.6, places=4)
        self.assertEqual(details["b.md"]["final_similarity"], 0.0)

    def test_remote_rerank_scores_are_probabilities(self) -> None:
        kb = _stub_kb([("a.md", "x")])
        kb._last_rerank_scale = "remote"
        self.assertEqual(kb._rerank_probabilities([0.02, 0.91]), [0.02, 0.91])
        kb._last_rerank_scale = "logit"
        probs = kb._rerank_probabilities([0.0, 4.0])
        self.assertAlmostEqual(probs[0], 0.5)
        self.assertGreater(probs[1], 0.98)

    def test_combine_scores_renormalizes_missing_parts(self) -> None:
        kb = _stub_kb([("a.md", "x")])
        self.assertAlmostEqual(kb._combine_scores(0.6, None), 0.6)
        self.assertAlmostEqual(kb._combine_scores(None, 0.8), 0.8)
        self.assertAlmostEqual(kb._combine_scores(0.4, 0.8), 0.35 * 0.4 + 0.65 * 0.8)
        self.assertEqual(kb._combine_scores(None, None), 0.0)

    def test_rerank_candidates_are_diversified_by_file(self) -> None:
        texts = [("long.md", f"段落{i}") for i in range(6)] + [("other.md", "别的"), ("third.md", "第三")]
        kb = _stub_kb(texts)
        kb.max_rerank_chunks_per_file = 2
        cands = [{"idx": i} for i in range(8)]
        picked = kb._diversify_for_rerank(cands, cap=4)
        picked_files = [kb._chunks[c["idx"]].filename for c in picked]
        self.assertEqual(len(picked), 4)
        self.assertEqual(picked_files.count("long.md"), 2)
        self.assertIn("other.md", picked_files)
        self.assertIn("third.md", picked_files)

    def test_diversify_backfills_when_few_files(self) -> None:
        kb = _stub_kb([("only.md", f"段落{i}") for i in range(6)])
        kb.max_rerank_chunks_per_file = 2
        picked = kb._diversify_for_rerank([{"idx": i} for i in range(6)], cap=4)
        # 只有一个文件时名额不浪费，按融合顺序补满
        self.assertEqual([c["idx"] for c in picked], [0, 1, 2, 3])

    def test_mixed_models_mark_unverified(self) -> None:
        import numpy as np

        kb = _stub_kb([("a.md", "x")])
        kb._embeddings = np.ones((1, 4), dtype=np.float32)
        kb._note_vectors_written(0)
        self.assertEqual(kb.embedding_consistency(), "verified")
        kb.embedding_model_name = "BAAI/bge-m3"
        kb._note_vectors_written(1)
        self.assertEqual(kb._index_embedding_model, kb._MIXED_EMBEDDING_MODEL)
        kb.embedding_model_name = "Qwen/Qwen3-Embedding-0.6B"
        self.assertEqual(kb.embedding_consistency(), "unverified")


if __name__ == "__main__":
    unittest.main()
