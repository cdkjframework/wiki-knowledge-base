"""P6：静态 UI 路径与 SPA fallback 规则。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class StaticUiTests(unittest.TestCase):
    def test_spa_fallback_rules(self) -> None:
        from src.api.static_ui import is_api_or_docs_path, should_spa_fallback

        self.assertTrue(should_spa_fallback("/"))
        self.assertTrue(should_spa_fallback("/retrieval-qa"))
        self.assertTrue(should_spa_fallback("/kb/management"))
        self.assertFalse(should_spa_fallback("/static/app.js"))
        self.assertFalse(should_spa_fallback("/favicon.ico"))
        self.assertTrue(should_spa_fallback("/api-docs"))
        self.assertTrue(is_api_or_docs_path("/api/query"))
        self.assertTrue(is_api_or_docs_path("/api/kb/documents"))
        self.assertTrue(is_api_or_docs_path("/health"))
        self.assertTrue(is_api_or_docs_path("/docs"))
        self.assertFalse(is_api_or_docs_path("/api-docs"))  # 已迁前端路由
        self.assertFalse(is_api_or_docs_path("/query"))  # 无前缀不再当 API
        self.assertFalse(is_api_or_docs_path("/overview"))

    def test_legacy_web_dir_prefers_archive(self) -> None:
        from src.api.static_ui import resolve_legacy_web_dir

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archived = root / "archive" / "web"
            archived.mkdir(parents=True)
            (archived / "index.html").write_text("ok", encoding="utf-8")
            (root / "web").mkdir()
            self.assertEqual(resolve_legacy_web_dir(root), archived)

    def test_legacy_disabled_by_default(self) -> None:
        from src.api.static_ui import legacy_web_enabled

        old = os.environ.pop("KB_SERVE_LEGACY_WEB", None)
        try:
            self.assertFalse(legacy_web_enabled())
            os.environ["KB_SERVE_LEGACY_WEB"] = "1"
            self.assertTrue(legacy_web_enabled())
        finally:
            if old is None:
                os.environ.pop("KB_SERVE_LEGACY_WEB", None)
            else:
                os.environ["KB_SERVE_LEGACY_WEB"] = old


if __name__ == "__main__":
    unittest.main()
