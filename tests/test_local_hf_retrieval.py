"""HuggingFace 本地 Embedding/Rerank 与运行时 apply。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock


class LocalHfProviderTests(unittest.TestCase):
    def test_normalize_base_url(self) -> None:
        from src.model_config_manager import (
            LOCAL_HF_BASE_URL,
            is_local_hf_provider,
            normalize_base_url_for_provider,
        )

        self.assertTrue(is_local_hf_provider("huggingface"))
        self.assertEqual(normalize_base_url_for_provider("huggingface", ""), LOCAL_HF_BASE_URL)
        self.assertEqual(
            normalize_base_url_for_provider("huggingface", None),
            LOCAL_HF_BASE_URL,
        )

    def test_providers_include_huggingface(self) -> None:
        from src.model_config_manager import ModelConfigManager

        mgr = object.__new__(ModelConfigManager)
        data = ModelConfigManager.get_supported_providers(mgr)
        names = {p["name"]: p for p in data["providers"]}
        self.assertIn("huggingface", names)
        self.assertTrue(names["huggingface"]["local_load"])
        self.assertEqual(names["huggingface"]["model_types"], ["embedding", "rerank"])

    def test_bootstrap_includes_local_hf(self) -> None:
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
        hf = [c for c in created if c.get("provider") == "huggingface"]
        types = {c.get("model_type") for c in hf}
        self.assertIn("embedding", types)
        self.assertIn("rerank", types)


class ApplyRetrievalBackendTests(unittest.TestCase):
    def test_apply_local_hf_embedding(self) -> None:
        from src.knowledge_base import KnowledgeBase

        kb = object.__new__(KnowledgeBase)
        kb.use_lm_studio_embeddings = True
        kb.embedding_model_name = "old-model"
        kb.dimension = 1024
        kb._embed_model = object()
        kb._embed_tokenizer = object()
        kb.lm_studio_base_url = "http://127.0.0.1:1234"
        kb.lm_studio_api_key = None
        kb.lm_studio_timeout = 30
        kb._lm_client = MagicMock()

        result = KnowledgeBase.apply_retrieval_backend(
            kb,
            kind="embedding",
            provider="huggingface",
            model_name="Qwen/Qwen3-Embedding-0.6B",
            dimension=1024,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "local_hf")
        self.assertFalse(kb.use_lm_studio_embeddings)
        self.assertEqual(kb.embedding_model_name, "Qwen/Qwen3-Embedding-0.6B")
        self.assertIsNone(kb._embed_model)

    def test_dimension_mismatch_warns(self) -> None:
        from src.knowledge_base import KnowledgeBase

        kb = object.__new__(KnowledgeBase)
        kb.use_lm_studio_embeddings = False
        kb.embedding_model_name = "Qwen/Qwen3-Embedding-0.6B"
        kb.dimension = 1024
        kb._embed_model = None
        kb._embed_tokenizer = None

        result = KnowledgeBase.apply_retrieval_backend(
            kb,
            kind="embedding",
            provider="huggingface",
            model_name="Qwen/Qwen3-Embedding-0.6B",
            dimension=3072,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])


class ApplyChatBackendTests(unittest.TestCase):
    def test_apply_openai_compat_chat(self) -> None:
        from src.knowledge_base import KnowledgeBase

        kb = object.__new__(KnowledgeBase)
        kb.use_lm_studio_chat = False
        kb.chat_model_name = "old-chat"
        kb.chat_temperature = 0.2
        kb.chat_max_tokens = 512
        kb.chat_local_files_only = True
        kb.lm_studio_timeout = 30
        kb.lm_studio_api_key = None
        kb.device = "cpu"
        kb.model_cache_dir = "."
        kb._chat_backend = MagicMock()
        kb._chat_backend._lm_client = None
        kb._unload_chat_model = MagicMock(return_value=True)

        result = KnowledgeBase.apply_chat_backend(
            kb,
            provider="qwen",
            model_name="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="sk-test",
            temperature=0.5,
            max_tokens=1024,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "openai_compat")
        self.assertEqual(result["kind"], "chat")
        self.assertTrue(kb.use_lm_studio_chat)
        self.assertEqual(kb.chat_model_name, "qwen-plus")
        self.assertEqual(kb.chat_temperature, 0.5)
        self.assertEqual(kb.chat_max_tokens, 1024)
        self.assertTrue(kb._chat_backend.use_lm_studio)
        self.assertIsNotNone(kb._chat_backend._lm_client)


if __name__ == "__main__":
    unittest.main()
