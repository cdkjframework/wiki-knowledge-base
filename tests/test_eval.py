"""KB-10 评测集：指标算法 / 题集解析 / 跑分与报告落盘。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.eval import cli as eval_cli
from src.eval.dataset import (
    DatasetError,
    default_dataset_path,
    load_dataset,
    parse_case,
)
from src.eval.metrics import (
    hit_at_k,
    matched_flags,
    ndcg_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from src.eval.runner import (
    REPORT_SCHEMA,
    make_kb_searcher,
    run_evaluation,
    save_report,
)


class MetricsTests(unittest.TestCase):
    def test_matched_flags_is_case_and_separator_insensitive(self) -> None:
        flags = matched_flags(["Docs\\A.MD", "b.md"], ["docs/a.md"])
        self.assertEqual(flags, [True, False])

    def test_matched_flags_allows_bare_filename_in_dataset(self) -> None:
        flags = matched_flags(["docs/guide.md"], ["guide.md"])
        self.assertEqual(flags, [True])

    def test_repeated_document_counts_once(self) -> None:
        flags = matched_flags(["a.md", "a.md", "b.md"], ["a.md", "b.md"])
        self.assertEqual(flags, [True, False, True])
        self.assertEqual(recall_at_k(flags, 2, 3), 1.0)

    def test_recall_at_k_windows_by_rank(self) -> None:
        flags = [False, False, True, False]
        self.assertEqual(recall_at_k(flags, 1, 2), 0.0)
        self.assertEqual(recall_at_k(flags, 1, 3), 1.0)

    def test_recall_is_capped_at_one(self) -> None:
        self.assertEqual(recall_at_k([True, True], 1, 5), 1.0)

    def test_precision_and_hit(self) -> None:
        flags = [True, False, False, False]
        self.assertAlmostEqual(precision_at_k(flags, 4), 0.25)
        self.assertEqual(hit_at_k(flags, 1), 1.0)
        self.assertEqual(hit_at_k([False, True], 1), 0.0)

    def test_reciprocal_rank(self) -> None:
        self.assertEqual(reciprocal_rank([False, True]), 0.5)
        self.assertEqual(reciprocal_rank([False, False]), 0.0)

    def test_ndcg_perfect_ranking_is_one(self) -> None:
        self.assertAlmostEqual(ndcg_at_k([True, True, False], 2, 10), 1.0)

    def test_ndcg_rewards_higher_rank(self) -> None:
        better = ndcg_at_k([True, False, False], 1, 10)
        worse = ndcg_at_k([False, False, True], 1, 10)
        self.assertGreater(better, worse)
        self.assertAlmostEqual(better, 1.0)

    def test_ndcg_without_positives_is_zero(self) -> None:
        self.assertEqual(ndcg_at_k([True], 0, 10), 0.0)

    def test_percentile_interpolates(self) -> None:
        self.assertEqual(percentile([10.0, 20.0, 30.0], 50), 20.0)
        self.assertEqual(percentile([], 95), 0.0)
        self.assertEqual(percentile([7.0], 95), 7.0)


class DatasetTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmp = Path(self._tmpdir.name) / "golden.jsonl"
        tmp.write_text(text, encoding="utf-8")
        return tmp

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_legacy_field_aliases_still_work(self) -> None:
        case = parse_case({"query": "退款", "expected_filename": "policy.md"}, 1)
        self.assertEqual(case.positives, ("policy.md",))
        case2 = parse_case({"query": "登录", "positive_filenames": ["a.md", "b.md"]}, 2)
        self.assertEqual(case2.positives, ("a.md", "b.md"))

    def test_missing_query_or_positives_raises(self) -> None:
        with self.assertRaises(DatasetError):
            parse_case({"positives": ["a.md"]}, 3)
        with self.assertRaises(DatasetError):
            parse_case({"query": "x"}, 4)

    def test_comments_and_blank_lines_skipped(self) -> None:
        path = self._write(
            "# 注释\n\n"
            '{"id":"a","query":"问题一","positives":["a.md"]}\n'
            '{"id":"b","query":"问题二","positives":["b.md"]}\n'
        )
        cases = load_dataset(path)
        self.assertEqual([c.id for c in cases], ["a", "b"])

    def test_duplicate_id_rejected(self) -> None:
        path = self._write(
            '{"id":"a","query":"一","positives":["a.md"]}\n'
            '{"id":"a","query":"二","positives":["b.md"]}\n'
        )
        with self.assertRaises(DatasetError):
            load_dataset(path)

    def test_id_defaults_to_line_number(self) -> None:
        path = self._write('{"query":"一","positives":["a.md"]}\n')
        self.assertEqual(load_dataset(path)[0].id, "case-0001")

    def test_empty_dataset_rejected(self) -> None:
        with self.assertRaises(DatasetError):
            load_dataset(self._write("# 只有注释\n"))

    def test_default_golden_set_meets_acceptance_size(self) -> None:
        cases = load_dataset(default_dataset_path())
        self.assertGreaterEqual(len(cases), 50)
        self.assertEqual(len({c.id for c in cases}), len(cases))


def _fake_searcher(table: dict[str, list[str]]):
    def _search(query: str, top_k: int) -> list[str]:
        return table.get(query, [])[:top_k]

    return _search


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cases = [
            parse_case({"id": "a", "query": "问题一", "positives": ["a.md"]}, 1),
            parse_case({"id": "b", "query": "问题二", "positives": ["b.md"]}, 2),
        ]

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_perfect_retrieval_scores_full_marks(self) -> None:
        report = run_evaluation(
            _fake_searcher({"问题一": ["a.md"], "问题二": ["b.md"]}), self.cases
        )
        summary = report["summary"]
        self.assertAlmostEqual(summary["recall@1"], 1.0)
        self.assertAlmostEqual(summary["ndcg@10"], 1.0)
        self.assertAlmostEqual(summary["mrr"], 1.0)
        self.assertEqual(summary["failed_count"], 0)

    def test_empty_retrieval_scores_zero(self) -> None:
        report = run_evaluation(_fake_searcher({}), self.cases)
        self.assertEqual(report["summary"]["recall@5"], 0.0)
        self.assertEqual(report["summary"]["mrr"], 0.0)

    def test_partial_retrieval_is_averaged(self) -> None:
        report = run_evaluation(
            _fake_searcher({"问题一": ["x.md", "a.md"], "问题二": []}), self.cases
        )
        self.assertAlmostEqual(report["summary"]["recall@1"], 0.0)
        self.assertAlmostEqual(report["summary"]["recall@3"], 0.5)
        self.assertAlmostEqual(report["summary"]["mrr"], 0.25)

    def test_search_error_does_not_abort_the_run(self) -> None:
        def _boom(query: str, top_k: int) -> list[str]:
            if query == "问题一":
                raise RuntimeError("索引挂了")
            return ["b.md"]

        report = run_evaluation(_boom, self.cases)
        self.assertEqual(report["summary"]["case_count"], 2)
        self.assertEqual(report["summary"]["failed_count"], 1)
        self.assertIn("索引挂了", report["cases"][0]["error"])
        self.assertTrue(report["cases"][1]["hit"])

    def test_report_carries_schema_and_latency(self) -> None:
        report = run_evaluation(_fake_searcher({"问题一": ["a.md"]}), self.cases)
        self.assertEqual(report["schema"], REPORT_SCHEMA)
        self.assertIn("p95", report["summary"]["latency_ms"])
        self.assertTrue(report["generated_at"])
        self.assertEqual(report["config"]["ndcg_k"], 10)

    def test_same_input_scores_are_reproducible(self) -> None:
        searcher = _fake_searcher({"问题一": ["a.md"], "问题二": ["x.md", "b.md"]})
        first = run_evaluation(searcher, self.cases)["summary"]
        second = run_evaluation(searcher, self.cases)["summary"]
        for key in ("recall@1", "recall@3", "recall@5", "ndcg@10", "mrr"):
            self.assertAlmostEqual(first[key], second[key], msg=key)

    def test_empty_dataset_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_evaluation(_fake_searcher({}), [])

    def test_save_report_also_refreshes_latest(self) -> None:
        report = run_evaluation(_fake_searcher({"问题一": ["a.md"]}), self.cases)
        out = Path(self._tmpdir.name) / "sub" / "report.json"
        saved = save_report(report, out)
        self.assertTrue(saved.exists())
        latest = out.parent / "latest.json"
        self.assertTrue(latest.exists())
        self.assertEqual(
            json.loads(latest.read_text(encoding="utf-8"))["schema"], REPORT_SCHEMA
        )


class KbSearcherAdapterTests(unittest.TestCase):
    class _StubKb:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int, float | None]] = []

        def search(self, query, k=None, relevance_threshold=None):
            self.calls.append((query, k, relevance_threshold))
            return [("a.md", "片段一", 0.31), ("b.md", "片段二", 0.62)]

    def test_adapter_keeps_only_filenames_in_rank_order(self) -> None:
        kb = self._StubKb()
        self.assertEqual(make_kb_searcher(kb)("问题", 5), ["a.md", "b.md"])

    def test_adapter_forwards_top_k_and_threshold(self) -> None:
        kb = self._StubKb()
        make_kb_searcher(kb, relevance_threshold=1.2)("问题", 7)
        self.assertEqual(kb.calls, [("问题", 7, 1.2)])


class CliTests(unittest.TestCase):
    def test_validate_accepts_default_golden_set(self) -> None:
        self.assertEqual(eval_cli.main(["--validate"]), 0)

    def test_validate_reports_broken_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.jsonl"
            bad.write_text('{"query": "缺答案"}\n', encoding="utf-8")
            self.assertEqual(eval_cli.main(["--validate", "--dataset", str(bad)]), 2)

    def test_missing_dataset_exits_with_code_two(self) -> None:
        self.assertEqual(
            eval_cli.main(["--validate", "--dataset", "no/such/file.jsonl"]), 2
        )


if __name__ == "__main__":
    unittest.main()
