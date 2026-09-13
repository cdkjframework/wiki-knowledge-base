"""KB-20：检索 / 分片参数校验与热更新逻辑。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class RetrievalSettingsTests(unittest.TestCase):
    def test_normalize_and_apply(self) -> None:
        from src.kb.retrieval_settings import (
            apply_settings_to_config,
            apply_settings_to_runtime,
            normalize_settings,
            snapshot_from_runtime,
        )

        current = {
            "default_k": 5,
            "max_search_results": 10,
            "min_source_similarity": 0.0,
            "chunk_size": 800,
            "chunk_overlap": 120,
        }
        settings = normalize_settings(
            {
                "default_k": 8,
                "max_search_results": 12,
                "min_source_similarity": 0.2,
                "chunk_size": 500,
                "chunk_overlap": 80,
            },
            current=current,
        )
        self.assertEqual(settings["default_k"], 8)
        self.assertEqual(settings["chunk_size"], 500)

        cfg: dict = {}
        apply_settings_to_config(cfg, settings)
        self.assertEqual(cfg["search"]["default_k"], 8)
        self.assertEqual(cfg["knowledge_base"]["chunking"]["size"], 500)

        kb = SimpleNamespace(default_k=2, max_search_results=3, chunk_size=800, chunk_overlap=120)
        search_cfg: dict = {"min_source_similarity": 0.55}
        apply_settings_to_runtime(kb, search_cfg, settings)
        snap = snapshot_from_runtime(kb, search_cfg)
        self.assertEqual(snap["default_k"], 8)
        self.assertEqual(snap["max_search_results"], 12)
        self.assertEqual(snap["min_source_similarity"], 0.2)
        self.assertEqual(snap["chunk_size"], 500)
        self.assertEqual(snap["chunk_overlap"], 80)
        self.assertEqual(snap["chunking_strategy"], "fixed")

    def test_reject_bad_ranges(self) -> None:
        from src.kb.retrieval_settings import normalize_settings

        with self.assertRaises(ValueError):
            normalize_settings({"default_k": 0})
        with self.assertRaises(ValueError):
            normalize_settings({"default_k": 10, "max_search_results": 5})
        with self.assertRaises(ValueError):
            normalize_settings({"chunk_size": 200, "chunk_overlap": 200})

    def test_api_hot_update_persists(self) -> None:
        """不启真服务：直接测 KnowledgeBaseApi 的读写路径。"""
        from src.api import http_server as hs

        original_write_path = hs.KnowledgeBaseApi._config_write_path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf_dir = root / "conf"
            conf_dir.mkdir()
            cfg_path = conf_dir / "config.json"
            cfg_path.write_text(
                '{"search":{"default_k":5,"max_search_results":10,"min_source_similarity":0.0},'
                '"knowledge_base":{"chunking":{"size":800,"overlap":120}}}\n',
                encoding="utf-8",
            )

            api = object.__new__(hs.KnowledgeBaseApi)
            api.kb = SimpleNamespace(
                default_k=5,
                max_search_results=10,
                chunk_size=800,
                chunk_overlap=120,
            )
            api._search_cfg = {
                "default_k": 5,
                "max_search_results": 10,
                "min_source_similarity": 0.0,
            }
            api._load_project_config = lambda: {  # type: ignore[method-assign]
                "search": dict(api._search_cfg),
                "knowledge_base": {"chunking": {"size": 800, "overlap": 120}},
            }
            try:
                hs.KnowledgeBaseApi._config_write_path = staticmethod(lambda: cfg_path)  # type: ignore[method-assign]

                before = api.get_retrieval_settings()
                self.assertEqual(before["default_k"], 5)

                after = api.update_retrieval_settings(
                    {
                        "default_k": 7,
                        "max_search_results": 15,
                        "min_source_similarity": 0.0,
                        "chunk_size": 600,
                        "chunk_overlap": 90,
                    }
                )
                self.assertEqual(after["default_k"], 7)
                self.assertEqual(api.kb.default_k, 7)
                self.assertEqual(api.kb.chunk_size, 600)
                self.assertEqual(api._search_cfg["max_search_results"], 15)
                self.assertEqual(api.default_search_k(), 7)

                text = cfg_path.read_text(encoding="utf-8")
                self.assertIn('"default_k": 7', text)
                self.assertIn('"size": 600', text)
            finally:
                hs.KnowledgeBaseApi._config_write_path = original_write_path  # type: ignore[method-assign]

    def test_settings_path_is_api(self) -> None:
        from src.api.static_ui import is_api_or_docs_path

        self.assertTrue(is_api_or_docs_path("/api/kb/settings"))
        self.assertTrue(is_api_or_docs_path("/api/kb/documents"))

    def test_handlers_get_put_settings(self) -> None:
        """模拟 HTTP 层：GET/PUT /kb/settings 走通 handler。"""
        from src.api.handlers.kb import handle_get_kb, handle_put_kb

        class FakeHttp:
            def __init__(self) -> None:
                self.payload = None
                self.status = None
                self.body = {
                    "default_k": 9,
                    "max_search_results": 12,
                    "min_source_similarity": 0.0,
                    "chunk_size": 700,
                    "chunk_overlap": 100,
                }

            def _ok(self, data, page_index=1):  # noqa: ANN001
                self.payload = data
                self.status = "ok"

            def _bad_request(self, msg):  # noqa: ANN001
                self.status = f"bad:{msg}"

            def _read_json(self):
                return self.body

            def _page_index_from_body(self, body):  # noqa: ANN001
                return 1

        class FakeApi:
            def __init__(self) -> None:
                self.kb = SimpleNamespace(
                    default_k=5,
                    max_search_results=10,
                    chunk_size=800,
                    chunk_overlap=120,
                )
                self._search_cfg = {
                    "default_k": 5,
                    "max_search_results": 10,
                    "min_source_similarity": 0.0,
                }

            def get_retrieval_settings(self):
                from src.kb.retrieval_settings import snapshot_from_runtime

                return snapshot_from_runtime(self.kb, self._search_cfg)

            def update_retrieval_settings(self, payload):
                from src.kb.retrieval_settings import (
                    apply_settings_to_runtime,
                    normalize_settings,
                    snapshot_from_runtime,
                )

                settings = normalize_settings(payload, current=self.get_retrieval_settings())
                apply_settings_to_runtime(self.kb, self._search_cfg, settings)
                return snapshot_from_runtime(self.kb, self._search_cfg)

            def default_search_k(self) -> int:
                return int(self.kb.default_k)

        http = FakeHttp()
        api = FakeApi()
        self.assertTrue(handle_get_kb(http, api, "/kb/settings"))
        self.assertEqual(http.status, "ok")
        self.assertEqual(http.payload["settings"]["default_k"], 5)

        self.assertTrue(handle_put_kb(http, api, "/kb/settings"))
        self.assertEqual(http.status, "ok")
        self.assertEqual(http.payload["settings"]["default_k"], 9)
        self.assertEqual(api.kb.default_k, 9)
        self.assertEqual(api.default_search_k(), 9)

    def test_resolve_top_k_follows_kb_default(self) -> None:
        from src.eval.cli import _resolve_top_k

        kb = SimpleNamespace(default_k=5, max_search_results=10)
        # 显式 CLI 优先
        self.assertEqual(_resolve_top_k(3, kb, [1, 3, 5], 10), 3)
        # 省略时：default_k=5，但指标需要 10 → 取 10
        self.assertEqual(_resolve_top_k(None, kb, [1, 3, 5, 10], 10), 10)
        # 指标只到 5 时跟 default_k
        kb2 = SimpleNamespace(default_k=8, max_search_results=20)
        self.assertEqual(_resolve_top_k(None, kb2, [1, 3, 5], 5), 8)

    def test_query_default_k_none(self) -> None:
        from src.api import http_server as hs

        api = object.__new__(hs.KnowledgeBaseApi)
        api.kb = SimpleNamespace(default_k=7)
        self.assertEqual(api.default_search_k(), 7)


if __name__ == "__main__":
    unittest.main()
