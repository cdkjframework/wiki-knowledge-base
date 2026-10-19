"""问答接口的证据门槛与确定性拒答：普通 / 流式同口径，且不调用生成模型。"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.chat.refusal import INSUFFICIENT_EVIDENCE_ANSWER
from src.kb.evidence_gate import EvidencePolicy

# 泛词误召回：只被 BM25 捞到、重排判不相关
_JUNK_DETAIL = {
    "filename": "银行电子凭证手册.pdf",
    "final_similarity": 0.62,
    "vector_similarity": 0.31,
    "embed_similarity": 0.31,
    "bm25_score": 4.2,
    "rerank_raw": -2.4,
    "rerank_similarity": 0.08,
    "rerank_status": "ok",
    "channels": ["bm25"],
}
_GOOD_DETAIL = {
    "filename": "报销制度.md",
    "final_similarity": 0.8,
    "vector_similarity": 0.66,
    "embed_similarity": 0.66,
    "bm25_score": 6.1,
    "rerank_raw": 2.1,
    "rerank_similarity": 0.89,
    "rerank_status": "ok",
    "channels": ["vector", "bm25"],
}


def _distance(sim: float) -> float:
    return (1.0 / sim) - 1.0


class _FakeKb:
    """按 relevance_threshold 返回不同结果，用来模拟 API 的无阈值回退。"""

    def __init__(self, rows: List[tuple], details: List[Dict[str, Any]], *, empty_with_threshold: bool = False):
        self._rows = rows
        self._details = details
        self._empty_with_threshold = empty_with_threshold
        self._last_search_details: List[Dict[str, Any]] = []
        self.evidence_policy = EvidencePolicy()
        self.calls: List[Any] = []

    def search(self, query: str, k: int | None = None, relevance_threshold: float | None = None):
        self.calls.append(relevance_threshold)
        if self._empty_with_threshold and relevance_threshold is not None:
            self._last_search_details = []
            return []
        self._last_search_details = [dict(d) for d in self._details]
        return list(self._rows)


def _api(kb: _FakeKb):
    from src.api.http_server import KnowledgeBaseApi

    api = KnowledgeBaseApi.__new__(KnowledgeBaseApi)
    api.kb = kb
    api._search_cfg = {"min_source_similarity": 0.0}
    api._chat_cfg = {}
    api._load_chat_context = lambda _u, _s: []
    api._append_history = MagicMock()
    api._answer_from_lm_studio = MagicMock(return_value=("模型回答", None, None))
    api._answer_stream_from_lm_studio = MagicMock(return_value=(iter(["模型", "回答"]), None))
    return api


def _junk_kb(**kw) -> _FakeKb:
    return _FakeKb(
        [("银行电子凭证手册.pdf", "本章内容介绍电子凭证开立。", _distance(0.62))],
        [_JUNK_DETAIL],
        **kw,
    )


class QueryEvidenceTests(unittest.TestCase):
    def test_no_evidence_returns_fixed_refusal_without_llm(self) -> None:
        api = _api(_junk_kb())
        resp = api.query("PMP内容", k=5)
        self.assertEqual(resp["answer"], INSUFFICIENT_EVIDENCE_ANSWER)
        self.assertEqual(resp["results"], [])
        self.assertEqual(resp["evidence_status"], "insufficient")
        api._answer_from_lm_studio.assert_not_called()

    def test_stream_matches_normal_refusal(self) -> None:
        api = _api(_junk_kb())
        data = api.query_stream("PMP内容", k=5)
        self.assertEqual(data["fixed_answer"], INSUFFICIENT_EVIDENCE_ANSWER)
        self.assertEqual(data["results"], [])
        self.assertEqual(data["evidence_status"], "insufficient")
        api._answer_stream_from_lm_studio.assert_not_called()

    def test_reliable_source_still_generates(self) -> None:
        kb = _FakeKb(
            [("报销制度.md", "报销需先提交申请，再由部门负责人审批。", _distance(0.8))],
            [_GOOD_DETAIL],
        )
        api = _api(kb)
        resp = api.query("报销流程", k=5)
        self.assertEqual(resp["answer"], "模型回答")
        self.assertEqual(resp["evidence_status"], "sufficient")
        self.assertEqual([r["filename"] for r in resp["results"]], ["报销制度.md"])
        item = resp["results"][0]
        self.assertEqual(item["rank"], 1)
        self.assertEqual(item["vector_similarity"], 0.66)
        self.assertEqual(item["bm25_score"], 6.1)
        self.assertEqual(item["rerank_status"], "ok")
        self.assertTrue(item["evidence"]["passed"])
        api._answer_from_lm_studio.assert_called_once()

    def test_gate_filters_mixed_batch_and_renumbers(self) -> None:
        kb = _FakeKb(
            [
                ("银行电子凭证手册.pdf", "本章内容介绍电子凭证开立。", _distance(0.62)),
                ("报销制度.md", "报销需先提交申请。", _distance(0.8)),
            ],
            [_JUNK_DETAIL, _GOOD_DETAIL],
        )
        resp = _api(kb).query("报销流程", k=5)
        self.assertEqual([r["filename"] for r in resp["results"]], ["报销制度.md"])
        self.assertEqual(resp["results"][0]["rank"], 1)

    def test_threshold_fallback_cannot_bypass_gate(self) -> None:
        kb = _junk_kb(empty_with_threshold=True)
        api = _api(kb)
        resp = api.query("PMP内容", k=5, relevance_threshold=0.2)
        # 先带阈值查空，再无阈值回退，回退结果仍被证据门槛拦下
        self.assertEqual(kb.calls, [0.2, None])
        self.assertTrue(resp["threshold_relaxed"])
        self.assertEqual(resp["results"], [])
        self.assertEqual(resp["answer"], INSUFFICIENT_EVIDENCE_ANSWER)

    def test_generate_answer_false_keeps_empty_contract(self) -> None:
        api = _api(_junk_kb())
        resp = api.query("PMP内容", k=5, generate_answer=False)
        self.assertEqual(resp["answer"], "")
        self.assertEqual(resp["finish_reason"], "not_requested")
        self.assertEqual(resp["results"], [])
        api._answer_from_lm_studio.assert_not_called()


class _FakeHttp:
    def __init__(self) -> None:
        self.events: List[tuple[str, Dict[str, Any]]] = []
        self.close_connection = False

    def _send_sse_headers(self) -> None:
        pass

    def _send_sse(self, event: str, payload: Dict[str, Any]) -> None:
        # 过一遍 JSON，确认事件体可以序列化
        self.events.append((event, json.loads(json.dumps(payload, ensure_ascii=False))))


class SseRefusalTests(unittest.TestCase):
    def test_sse_emits_meta_delta_done_for_refusal(self) -> None:
        from src.api.handlers.sse_query import write_query_sse

        api = _api(_junk_kb())
        http = _FakeHttp()
        write_query_sse(
            http,
            api,
            query="PMP内容",
            k=5,
            relevance_threshold=None,
            llm_model=None,
            model_config_id=None,
            model_config_name=None,
            use_default_model_config=True,
            generate_answer=True,
            temperature=0.2,
            max_tokens=None,
            user_id=None,
            session_id=None,
            deep_think=True,
            enable_mcp_auto=False,
        )
        names = [name for name, _ in http.events]
        self.assertEqual(names, ["meta", "delta", "done"])
        meta, delta, done = (payload for _, payload in http.events)
        self.assertEqual(meta["results"], [])
        self.assertEqual(meta["evidence_status"], "insufficient")
        self.assertEqual(delta["delta"], INSUFFICIENT_EVIDENCE_ANSWER)
        self.assertEqual(done["answer"], INSUFFICIENT_EVIDENCE_ANSWER)
        self.assertEqual(done["finish_reason"], "stop")
        # deep_think 开着也不能冒出思考内容
        self.assertFalse(done["thinking"])
        api._answer_stream_from_lm_studio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
