"""P5：deep_think 策略与 edition 门控单测。"""

from __future__ import annotations

import os
import unittest


class DeepThinkStrategyTests(unittest.TestCase):
    def test_disabled_returns_unchanged(self) -> None:
        from src.chat.deep_think import apply_deep_thinking_strategy

        prompt = "你是助手"
        self.assertEqual(
            apply_deep_thinking_strategy(prompt, deep_think=False, model_type="qwen"),
            prompt,
        )
        self.assertNotIn("<think>", prompt)

    def test_qwen_injects_think_tags(self) -> None:
        from src.chat.deep_think import apply_deep_thinking_strategy

        out = apply_deep_thinking_strategy("BASE", deep_think=True, model_type="qwen")
        self.assertIn("<think>", out)
        self.assertIn("<thinking_summary>", out)
        self.assertTrue(out.startswith("BASE"))


class BoolParamsTests(unittest.TestCase):
    def test_parse_deep_think_default_false(self) -> None:
        from src.api.bool_params import parse_deep_think

        self.assertFalse(parse_deep_think(None))
        self.assertFalse(parse_deep_think(False))
        self.assertTrue(parse_deep_think("true"))
        with self.assertRaises(ValueError):
            parse_deep_think("maybe")


class HandlerDispatchTests(unittest.TestCase):
    def test_handlers_ignore_unmatched_paths(self) -> None:
        from src.api.handlers import (
            handle_get_history,
            handle_get_kb,
            handle_get_mcp,
            handle_get_model,
            handle_get_query,
            handle_get_session,
            handle_get_stats,
            handle_post_query,
        )

        class Dummy:
            pass

        http = Dummy()
        api = Dummy()
        self.assertFalse(handle_get_query(http, api, "/health"))
        self.assertFalse(handle_get_stats(http, api, "/health"))
        self.assertFalse(handle_get_kb(http, api, "/health"))
        self.assertFalse(handle_get_history(http, api, "/health"))
        self.assertFalse(handle_get_session(http, api, "/health"))
        self.assertFalse(handle_get_model(http, api, "/health"))
        self.assertFalse(handle_get_mcp(http, api, "/health"))
        self.assertFalse(handle_post_query(http, api, "/session", {}))

    def test_model_default_path_order(self) -> None:
        """/model/config/default 不得被当成 name=default。"""
        from src.api.handlers.model import handle_get_model

        calls: list[str] = []

        class Api:
            _model_config_manager = type(
                "M",
                (),
                {
                    "get_default_config": lambda self: calls.append("default") or {"ok": True},
                    "get_model_config": lambda self, **kw: calls.append(f"get:{kw}") or {"ok": True},
                },
            )()

        class Http:
            def _ok(self, payload):
                calls.append(("ok", payload))

            def _bad_request(self, msg):
                calls.append(("bad", msg))

        self.assertTrue(handle_get_model(Http(), Api(), "/model/config/default"))
        self.assertIn("default", calls)
        self.assertTrue(any(c == "default" or (isinstance(c, tuple) and c[0] == "ok") for c in calls))
        self.assertFalse(any(isinstance(c, str) and c.startswith("get:") for c in calls))


class EditionPackagingTests(unittest.TestCase):
    def test_build_edition_community_excludes_business(self) -> None:
        import tempfile
        from pathlib import Path

        from scripts.build_edition import stage_edition, verify_staged

        with tempfile.TemporaryDirectory() as tmp:
            staged = stage_edition("community", Path(tmp) / "community")
            errors = verify_staged("community", staged)
            self.assertEqual(errors, [])
            self.assertFalse((staged / "src" / "commercial" / "business").exists())
            self.assertTrue((staged / "src" / "commercial" / "edition.py").is_file())
            self.assertFalse((staged / "scripts").exists())
            self.assertFalse((staged / ".github").exists())
            self.assertTrue((staged / "tests").is_dir())

    def test_build_edition_commercial_keeps_business(self) -> None:
        import tempfile
        from pathlib import Path

        from scripts.build_edition import stage_edition, verify_staged

        with tempfile.TemporaryDirectory() as tmp:
            staged = stage_edition("commercial", Path(tmp) / "commercial")
            errors = verify_staged("commercial", staged)
            self.assertEqual(errors, [])
            self.assertTrue((staged / "src" / "commercial" / "business" / "__init__.py").is_file())

    def test_business_requires_commercial_edition(self) -> None:
        from src.commercial.business import ping_commercial_runtime

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "community"
        try:
            with self.assertRaises(PermissionError):
                ping_commercial_runtime()
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old


class EditionGateTests(unittest.TestCase):
    def test_community_blocks_commercial_feature(self) -> None:
        from src.commercial.edition import feature_enabled, get_edition

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "community"
        try:
            self.assertEqual(get_edition(), "community")
            self.assertTrue(feature_enabled("KB-01"))
            self.assertFalse(feature_enabled("KB-03"))
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old

    def test_commercial_enables_rbac(self) -> None:
        from src.commercial.edition import feature_enabled

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "commercial"
        try:
            self.assertTrue(feature_enabled("KB-04"))
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old

    def test_community_disables_ocr_feature(self) -> None:
        from src.commercial.edition import feature_enabled, ocr_allowed

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "community"
        try:
            self.assertFalse(feature_enabled("KB-16"))
            self.assertFalse(ocr_allowed())
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old

    def test_commercial_enables_ocr_feature(self) -> None:
        from src.commercial.edition import feature_enabled, ocr_allowed

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "commercial"
        try:
            self.assertTrue(feature_enabled("KB-16"))
            self.assertTrue(ocr_allowed())
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old

    def test_ocr_parser_forced_off_in_community(self) -> None:
        from pathlib import Path

        from src.document_parsers.ocr_parser import DisabledOcrParser, create_ocr_parser

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "community"
        try:
            parser = create_ocr_parser(
                {"enabled": True, "engine": "paddleocr"},
                model_cache_dir=Path("."),
            )
            self.assertIsInstance(parser, DisabledOcrParser)
            self.assertFalse(parser.enabled)
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old

    def test_ocr_parser_lives_in_commercial_business(self) -> None:
        from pathlib import Path

        from src.commercial.business.ocr import OcrParser
        from src.document_parsers.ocr_parser import create_ocr_parser

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "commercial"
        try:
            parser = create_ocr_parser(
                {"enabled": True, "engine": "paddleocr"},
                model_cache_dir=Path("."),
            )
            self.assertIsInstance(parser, OcrParser)
            self.assertTrue(parser.enabled)
            parser_off = create_ocr_parser(
                {"enabled": False, "engine": "paddleocr"},
                model_cache_dir=Path("."),
            )
            self.assertIsInstance(parser_off, OcrParser)
            self.assertFalse(parser_off.enabled)
            with self.assertRaises(PermissionError):
                # 直接构造也会被 require_commercial 挡住（切社区）
                os.environ["KB_EDITION"] = "community"
                OcrParser({"enabled": True}, model_cache_dir=Path("."))
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old


    def test_community_disables_semantic_chunking(self) -> None:
        from src.commercial.edition import feature_enabled, semantic_chunking_allowed

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "community"
        try:
            self.assertFalse(feature_enabled("KB-02"))
            self.assertFalse(semantic_chunking_allowed())
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old

    def test_commercial_semantic_chunk_keeps_heading_boundary(self) -> None:
        from src.commercial.business.chunking import split_semantic

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "commercial"
        try:
            text = (
                "# 第一章\n"
                + ("甲" * 200)
                + "。\n\n"
                + "# 第二章\n"
                + ("乙" * 200)
                + "。"
            )
            parts = split_semantic(text, chunk_size=300, chunk_overlap=40)
            self.assertGreaterEqual(len(parts), 2)
            joined = "\n".join(parts)
            self.assertIn("第一章", joined)
            self.assertIn("第二章", joined)
            # 两章不应被糊成完全看不出标题边界的一整坨
            self.assertTrue(any("第一章" in p for p in parts))
            self.assertTrue(any("第二章" in p for p in parts))
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old

    def test_semantic_chunk_requires_commercial(self) -> None:
        from src.commercial.business.chunking import split_semantic

        old = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "community"
        try:
            with self.assertRaises(PermissionError):
                split_semantic("短文本即可。", chunk_size=800, chunk_overlap=120)
        finally:
            if old is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old


if __name__ == "__main__":
    unittest.main()
