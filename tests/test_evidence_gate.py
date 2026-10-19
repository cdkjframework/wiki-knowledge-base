"""证据门槛与查询词治理：PMP 误召回修复的核心判定。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.kb.evidence_gate import (
    STATUS_INSUFFICIENT,
    STATUS_SUFFICIENT,
    EvidencePolicy,
    evaluate_evidence,
)
from src.kb.query_terms import (
    extract_entities,
    is_entity_token,
    load_aliases_file,
    tokenize_query,
)


class QueryTermsTests(unittest.TestCase):
    def test_pmp_content_keeps_only_entity(self) -> None:
        self.assertEqual(tokenize_query("PMP内容"), ["pmp"])

    def test_entity_with_digits_is_kept(self) -> None:
        self.assertEqual(tokenize_query("ISO9001资料"), ["iso9001"])

    def test_plain_chinese_question_keeps_char_and_bigram(self) -> None:
        tokens = tokenize_query("报销流程怎么走")
        for expected in ("报", "销", "报销", "流程"):
            self.assertIn(expected, tokens)
        # 泛词被剥掉，双字也不跨过被剥的位置
        self.assertNotIn("怎么", tokens)
        self.assertNotIn("程走", tokens)

    def test_only_generic_words_yield_nothing(self) -> None:
        self.assertEqual(tokenize_query("内容"), [])
        self.assertEqual(tokenize_query("是什么"), [])

    def test_entity_query_drops_chinese_unigrams(self) -> None:
        tokens = tokenize_query("PMP考试报名")
        self.assertIn("pmp", tokens)
        self.assertIn("考试", tokens)
        self.assertNotIn("考", tokens)

    def test_latin_tokens_follow_index_tokenizer(self) -> None:
        # 索引端把 KB-10 切成 kb / 10，查询端必须一致才对得上
        tokens = tokenize_query("KB-10 验收标准")
        self.assertIn("kb", tokens)
        self.assertIn("10", tokens)

    def test_entity_detection(self) -> None:
        self.assertTrue(is_entity_token("PMP"))
        self.assertTrue(is_entity_token("KB-10"))
        self.assertTrue(is_entity_token("v1.1"))
        self.assertFalse(is_entity_token("license"))
        self.assertFalse(is_entity_token("A"))
        self.assertEqual(extract_entities("PMP 和 license 以及 ISO9001"), ["pmp", "iso9001"])

    def test_aliases_file_is_lenient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "a.json"
            good.write_text(
                json.dumps({"aliases": {"PMP": ["项目管理专业人士"]}}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(load_aliases_file(good), {"pmp": ["项目管理专业人士"]})
            bad = Path(tmp) / "b.json"
            bad.write_text("{坏掉的 json", encoding="utf-8")
            self.assertEqual(load_aliases_file(bad), {})
        self.assertEqual(load_aliases_file(Path("no/such/file.json")), {})


def _item(**kw):
    base = {"filename": "doc.md", "text": ""}
    base.update(kw)
    return base


class EvidenceGateTests(unittest.TestCase):
    def test_generic_hit_without_semantic_evidence_is_rejected(self) -> None:
        # 只靠 BM25「内容」捞上来、重排也不认：PMP内容 的原始误召回场景
        item = _item(
            filename="银行电子凭证手册.pdf",
            text="本章内容介绍电子凭证的开立流程。",
            vector_similarity=0.32,
            rerank_similarity=0.08,
            rerank_status="ok",
            channels=["bm25"],
        )
        decision = evaluate_evidence("PMP内容", [item])
        self.assertEqual(decision.passed, [])
        self.assertEqual(decision.status, STATUS_INSUFFICIENT)
        self.assertFalse(item["evidence"]["passed"])

    def test_bm25_only_without_rerank_is_rejected(self) -> None:
        item = _item(
            text="随便什么内容",
            vector_similarity=None,
            rerank_similarity=None,
            rerank_status="failed",
        )
        decision = evaluate_evidence("报销流程", [item])
        self.assertEqual(decision.passed, [])
        self.assertIn("缺少语义证据", item["evidence"]["reason"])

    def test_rerank_relevant_passes(self) -> None:
        item = _item(
            text="报销需要先在系统提交申请。",
            vector_similarity=0.55,
            rerank_similarity=0.83,
            rerank_status="ok",
        )
        decision = evaluate_evidence("报销流程", [item])
        self.assertEqual(decision.status, STATUS_SUFFICIENT)
        self.assertEqual(item["evidence"]["basis"], "rerank")

    def test_vector_evidence_passes_when_rerank_disabled(self) -> None:
        item = _item(text="报销流程说明", vector_similarity=0.62, rerank_status="disabled")
        self.assertEqual(len(evaluate_evidence("报销流程", [item]).passed), 1)
        weak = _item(text="报销流程说明", vector_similarity=0.3, rerank_status="disabled")
        self.assertEqual(evaluate_evidence("报销流程", [weak]).passed, [])

    def test_strong_vector_overrides_low_rerank(self) -> None:
        item = _item(
            text="报销流程说明",
            vector_similarity=0.8,
            rerank_similarity=0.2,
            rerank_status="ok",
        )
        self.assertEqual(evaluate_evidence("报销流程", [item]).passed[0]["evidence"]["basis"], "vector_strong")

    def test_entity_alias_counts_as_match(self) -> None:
        policy = EvidencePolicy.from_config({}, aliases={"PMP": ["项目管理专业人士"]})
        item = _item(
            text="项目管理专业人士认证要求 35 学时培训。",
            vector_similarity=0.5,
            rerank_similarity=0.6,
            rerank_status="ok",
        )
        decision = evaluate_evidence("PMP 报考条件", [item], policy)
        self.assertEqual(len(decision.passed), 1)
        self.assertTrue(item["evidence"]["entity_matched"])

    def test_entity_missing_needs_stronger_rerank(self) -> None:
        # 没写缩写、但确实在解释 PMP：重排足够有把握时照样放行，不做逐字硬匹配
        explaining = _item(
            text="该认证由美国项目管理协会颁发，考察项目管理知识体系。",
            vector_similarity=0.6,
            rerank_similarity=0.9,
            rerank_status="ok",
        )
        lukewarm = _item(
            text="项目周报模板",
            vector_similarity=0.6,
            rerank_similarity=0.6,
            rerank_status="ok",
        )
        decision = evaluate_evidence("PMP是什么", [explaining, lukewarm])
        self.assertEqual(decision.passed, [explaining])
        self.assertEqual(explaining["evidence"]["basis"], "rerank_strict")
        self.assertFalse(lukewarm["evidence"]["entity_matched"])

    def test_filename_counts_for_entity(self) -> None:
        item = _item(
            filename="WIKI_PRD_功能重新规划.md",
            text="核心用户场景如下。",
            vector_similarity=0.6,
            rerank_similarity=0.7,
            rerank_status="ok",
        )
        self.assertEqual(len(evaluate_evidence("PRD 里定义的核心用户场景", [item]).passed), 1)

    def test_disabled_policy_passes_everything(self) -> None:
        policy = EvidencePolicy.from_config({"enabled": False})
        item = _item(vector_similarity=None, rerank_status="failed")
        decision = evaluate_evidence("PMP内容", [item], policy)
        self.assertEqual(decision.passed, [item])
        self.assertEqual(item["evidence"]["basis"], "disabled")

    def test_policy_from_config_clamps_and_merges_aliases(self) -> None:
        policy = EvidencePolicy.from_config(
            {
                "min_rerank_probability": 1.7,
                "min_vector_similarity": "abc",
                "aliases": {"RAG": ["检索增强生成"]},
                "extra_generic_terms": ["帮我查"],
            },
            aliases={"PMP": ["项目管理专业人士"]},
        )
        self.assertEqual(policy.min_rerank_probability, 1.0)
        self.assertEqual(policy.min_vector_similarity, 0.5)
        self.assertIn("pmp", policy.aliases)
        self.assertIn("rag", policy.aliases)
        self.assertEqual(policy.extra_generic_terms, ("帮我查",))


if __name__ == "__main__":
    unittest.main()
