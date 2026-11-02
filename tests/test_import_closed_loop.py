"""KB-16 共用导入闭环：上传 → 解析 → 索引 → 检索/原文件读回。

不启真 embedding / OCR 模型；文字层导入与空解析提示是本切片验收重点。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np


def _make_import_kb(tmp: str):
    """最小可写 KB：真解析器 + 打桩向量，避免拉模型。"""
    from src.document_parsers import KnowledgeBaseDocumentParser
    from src.kb.evidence_gate import EvidencePolicy
    from src.knowledge_base import KnowledgeBase

    root = Path(tmp)
    kb = object.__new__(KnowledgeBase)
    kb.persist_dir = root
    kb.documents_dir = root / "documents"
    kb.documents_dir.mkdir(parents=True, exist_ok=True)
    kb.meta_path = root / "meta.json"
    kb.chunks_path = root / "chunks.jsonl"
    kb.embeddings_path = root / "embeddings.npy"
    kb.index_path = root / "index.faiss"
    kb.vector_backend = "numpy"
    kb.dimension = 4
    kb.chunk_size = 200
    kb.chunk_overlap = 20
    kb.default_k = 5
    kb.max_search_results = 10
    kb.candidate_multiplier = 2
    kb.min_candidates = 3
    kb.embed_weight = 1.0
    kb.rerank_weight = 0.0
    kb.hybrid_enabled = True
    kb.rrf_k = 60
    kb.max_rerank_candidates = 8
    kb.max_rerank_chunks_per_file = 3
    kb.evidence_policy = EvidencePolicy(enabled=False)
    kb.embedding_model_name = "test-embed"
    kb.reranker_model_name = ""
    kb._index_embedding_model = "test-embed"
    kb.use_lm_studio_embeddings = False
    kb._faiss_use_gpu = False
    kb._chunks = []
    kb._embeddings = np.zeros((0, 4), dtype=np.float32)
    kb._index = None
    kb._bm25 = None
    kb._document_parser = KnowledgeBaseDocumentParser(
        ocr_config={"enabled": False, "enable_marker": False, "enable_pix2text": False}
    )
    return kb


def _unit_embed(texts: List[str]) -> np.ndarray:
    n = len(texts)
    if n == 0:
        return np.zeros((0, 4), dtype=np.float32)
    # 各行不同一点，方便向量通道也能区分；BM25 才是本测主通道
    out = np.zeros((n, 4), dtype=np.float32)
    for i in range(n):
        out[i, i % 4] = 1.0
    return out


class EmptyExtractTests(unittest.TestCase):
    def test_empty_bytes_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = _make_import_kb(tmp)
            with self.assertRaises(ValueError) as ctx:
                kb.add_uploaded_file("a.md", b"")
            self.assertIn("内容为空", str(ctx.exception))

    def test_image_without_ocr_rejected_with_kb16_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = _make_import_kb(tmp)
            # 假 PNG 头，足够让图片路径走到 OCR 桩并返回空串
            payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
            with self.assertRaises(ValueError) as ctx:
                kb.add_uploaded_file("scan.png", payload)
            msg = str(ctx.exception)
            self.assertIn("未能从「scan.png」提取到可用文字", msg)
            self.assertIn("KB-16", msg)


class ImportClosedLoopTests(unittest.TestCase):
    def test_upload_chunk_search_original(self) -> None:
        from src.api.http_server import KnowledgeBaseApi
        from src.kb.bm25_index import build_bm25

        body = (
            "# 导入闭环验收\n\n"
            "WIKI 本地知识库支持文件上传、解析入库与检索引用读回。\n"
            "本段用于核对共用导入合同。\n"
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            kb = _make_import_kb(tmp)
            with (
                patch.object(kb, "_embed_texts", side_effect=_unit_embed),
                patch.object(kb, "_rebuild_index", return_value=None),
                patch.object(kb, "_save", return_value=None),
            ):
                chunks = kb.add_uploaded_file("闭环验收.md", body)
                self.assertGreater(chunks, 0)
                self.assertTrue(any(c.filename == "闭环验收.md" for c in kb._chunks))

                # 原文件必须落盘，供控制台预览/下载
                original = kb.get_original_path("闭环验收.md")
                self.assertIsNotNone(original)
                assert original is not None
                self.assertEqual(original.read_bytes(), body)

                listed = kb.list_chunks(page_index=1, page_size=20, filename="闭环验收.md")
                self.assertGreaterEqual(int(listed["count"]), 1)

                kb._bm25 = build_bm25([c.text for c in kb._chunks])
                hits = kb.search("共用导入合同", k=3, relevance_threshold=None)
                self.assertTrue(hits)
                self.assertEqual(hits[0][0], "闭环验收.md")
                self.assertIn("导入", hits[0][1])

                api = KnowledgeBaseApi.__new__(KnowledgeBaseApi)
                api.kb = kb
                api._search_cfg = {"min_source_similarity": 0.0}
                api._chat_cfg = {}
                api._is_internal_mcp_filename = lambda _n: False  # type: ignore[method-assign]
                info = api.get_document_original("闭环验收.md", prefer_text=True)
                self.assertTrue(info.get("is_text"))
                self.assertIn("导入闭环验收", str(info.get("content") or ""))

                upload_resp = api.add_uploaded_file("闭环验收.md", body)
                self.assertTrue(upload_resp["ok"])
                self.assertGreater(int(upload_resp["chunks_added"]), 0)

    def test_api_propagates_empty_extract(self) -> None:
        from src.api.http_server import KnowledgeBaseApi

        with tempfile.TemporaryDirectory() as tmp:
            kb = _make_import_kb(tmp)
            api = KnowledgeBaseApi.__new__(KnowledgeBaseApi)
            api.kb = kb
            with self.assertRaises(ValueError) as ctx:
                api.add_uploaded_file("空白.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
            self.assertIn("KB-16", str(ctx.exception))


class QueryCitationAfterImportTests(unittest.TestCase):
    """导入后问答来源引用：不调大模型，只核对检索结果能回传 filename。"""

    def test_query_sources_include_imported_file(self) -> None:
        from src.api.http_server import KnowledgeBaseApi
        from src.kb.evidence_gate import EvidencePolicy

        details = [
            {
                "filename": "闭环验收.md",
                "final_similarity": 0.9,
                "vector_similarity": 0.8,
                "embed_similarity": 0.8,
                "bm25_score": 5.0,
                "rerank_raw": 0.9,
                "rerank_similarity": 0.9,
                "rerank_status": "ok",
                "channels": ["vector", "bm25"],
            }
        ]

        class _Kb:
            def __init__(self) -> None:
                self._last_search_details = [dict(details[0])]
                self.evidence_policy = EvidencePolicy(enabled=False)

            def search(self, query: str, k=None, relevance_threshold=None):  # noqa: ANN001
                return [("闭环验收.md", "WIKI 共用导入合同核对片段", 0.1)]

        api = KnowledgeBaseApi.__new__(KnowledgeBaseApi)
        api.kb = _Kb()
        api._search_cfg = {"min_source_similarity": 0.0}
        api._chat_cfg = {}
        api._load_chat_context = lambda _u, _s: []
        api._append_history = MagicMock()
        api._answer_from_lm_studio = MagicMock(return_value=("占位回答", None, None))

        resp = api.query("共用导入合同", k=3, generate_answer=False)
        self.assertEqual(resp["evidence_status"], "sufficient")
        self.assertEqual(resp["results"][0]["filename"], "闭环验收.md")
        api._answer_from_lm_studio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
