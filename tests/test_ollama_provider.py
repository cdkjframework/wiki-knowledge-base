"""Ollama 作为知识库分析模型服务商。"""

from __future__ import annotations

import unittest


class OllamaProviderTests(unittest.TestCase):
    def test_endpoint_and_from_provider(self) -> None:
        from src.universal_llm_client import UniversalLLMClient

        self.assertIn("ollama", UniversalLLMClient.PROVIDER_ENDPOINTS)
        self.assertEqual(
            UniversalLLMClient.PROVIDER_ENDPOINTS["ollama"],
            "http://127.0.0.1:11434/v1",
        )
        client = UniversalLLMClient.from_provider("ollama", api_key=None)
        self.assertEqual(client.provider, "ollama")
        self.assertTrue(str(client.base_url).rstrip("/").endswith("/v1"))

    def test_detect_by_port(self) -> None:
        from src.universal_llm_client import UniversalLLMClient

        client = UniversalLLMClient(base_url="http://127.0.0.1:11434/v1")
        self.assertEqual(client.provider, "ollama")
        # 非 11434 的本机仍按 LM Studio 习惯识别
        lm = UniversalLLMClient(base_url="http://127.0.0.1:1234/v1")
        self.assertEqual(lm.provider, "lm_studio")

    def test_providers_api_no_key_required(self) -> None:
        from src.model_config_manager import ModelConfigManager

        mgr = object.__new__(ModelConfigManager)
        data = ModelConfigManager.get_supported_providers(mgr)
        names = {p["name"]: p for p in data["providers"]}
        self.assertIn("ollama", names)
        self.assertFalse(names["ollama"]["requires_api_key"])
        self.assertEqual(names["ollama"]["base_url"], "http://127.0.0.1:11434/v1")

    def test_bootstrap_includes_ollama_chat(self) -> None:
        from src.model_config_manager import ModelConfigManager

        created: list[dict] = []

        class EmptyStore:
            def get_config_by_name(self, name):  # noqa: ANN001
                return None

        def fake_add(**kwargs):  # noqa: ANN003
            created.append(kwargs)
            return {"ok": True}

        mgr = object.__new__(ModelConfigManager)
        mgr.store = EmptyStore()  # type: ignore[attr-defined]
        mgr._client_cache = {}
        mgr.add_model_config = fake_add  # type: ignore[method-assign]
        ModelConfigManager.bootstrap_default_configs(mgr)
        ollama_rows = [c for c in created if c.get("provider") == "ollama"]
        self.assertTrue(ollama_rows)
        self.assertEqual(ollama_rows[0].get("model_type"), "chat")


if __name__ == "__main__":
    unittest.main()
