"""API 公共前缀 /api。"""

from __future__ import annotations

import os
import unittest


class ApiPrefixTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("KB_API_PREFIX", None)

    def test_strip_default_prefix(self) -> None:
        from src.api.api_prefix import strip_api_prefix, with_api_prefix

        self.assertEqual(strip_api_prefix("/api/query"), "/query")
        self.assertEqual(strip_api_prefix("/api/kb/documents"), "/kb/documents")
        self.assertEqual(strip_api_prefix("/api"), "/")
        self.assertIsNone(strip_api_prefix("/query"))
        self.assertEqual(with_api_prefix("/query"), "/api/query")

    def test_custom_prefix_env(self) -> None:
        os.environ["KB_API_PREFIX"] = "/api/v1"
        from importlib import reload
        import src.api.api_prefix as mod

        reload(mod)
        self.assertEqual(mod.strip_api_prefix("/api/v1/stats"), "/stats")
        self.assertIsNone(mod.strip_api_prefix("/api/stats"))
        reload(mod)  # 恢复默认（env 仍在则…）
        os.environ.pop("KB_API_PREFIX", None)
        reload(mod)


if __name__ == "__main__":
    unittest.main()
