"""P3：model_type 归一化与 bootstrap 种子覆盖三类。"""

from __future__ import annotations

import unittest


class NormalizeModelTypeTests(unittest.TestCase):
    def test_aliases(self) -> None:
        from src.model_config_manager import normalize_model_type

        self.assertEqual(normalize_model_type("embed"), "embedding")
        self.assertEqual(normalize_model_type("EMBEDDING"), "embedding")
        self.assertEqual(normalize_model_type("reranker"), "rerank")
        self.assertEqual(normalize_model_type("analysis"), "chat")
        self.assertEqual(normalize_model_type(None), "chat")
        self.assertEqual(normalize_model_type("weird", default="embedding"), "embedding")


class BootstrapPresetCoverageTests(unittest.TestCase):
    def test_presets_cover_three_kinds(self) -> None:
        """不连库：直接检查 bootstrap 源列表构造逻辑覆盖三类。"""
        from src.model_config_manager import ModelConfigManager, normalize_model_type

        # 用空对象骗过 __init__ 不碰 DB：只读方法体里的 presets 定义太重；
        # 改为反射 bootstrap 的预期：调用时 store 会被访问，故用桩。
        class FakeStore:
            def get_config_by_name(self, name):  # noqa: ANN001
                return {"name": name}  # 全部视为已存在 → skipped

        mgr = object.__new__(ModelConfigManager)
        mgr.store = FakeStore()  # type: ignore[attr-defined]
        mgr._client_cache = {}
        result = ModelConfigManager.bootstrap_default_configs(mgr)
        self.assertTrue(result.get("ok"))
        self.assertIn("message", result)
        # 全部 skipped，但至少说明种子名列表跑通
        self.assertGreaterEqual(result.get("count_skipped", 0), 8)

        # 再测「空库」路径：收集将要创建的 type
        created_types: list[str] = []

        class EmptyStore:
            def get_config_by_name(self, name):  # noqa: ANN001
                return None

        def fake_add(**kwargs):  # noqa: ANN003
            created_types.append(normalize_model_type(kwargs.get("model_type")))
            return {"ok": True}

        mgr2 = object.__new__(ModelConfigManager)
        mgr2.store = EmptyStore()  # type: ignore[attr-defined]
        mgr2._client_cache = {}
        mgr2.add_model_config = fake_add  # type: ignore[method-assign]
        ModelConfigManager.bootstrap_default_configs(mgr2)
        self.assertIn("chat", created_types)
        self.assertIn("embedding", created_types)
        self.assertIn("rerank", created_types)


if __name__ == "__main__":
    unittest.main()
