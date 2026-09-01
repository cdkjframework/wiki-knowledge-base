"""KB-11 指标看板：报告读取 / KPI 整形 / HTTP 路由。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, List, Tuple

from src.eval.dataset import parse_case
from src.eval.reports import list_reports, load_latest, summarize
from src.eval.runner import REPORT_SCHEMA, run_evaluation, save_report
from src.metrics.dashboard import build_dashboard


def _make_report(recall: float = 1.0, latency_ms: float = 0.0) -> dict:
    """用真跑分产出报告，顺带证明看板读的就是 KB-10 的输出格式。"""
    cases = [
        parse_case({"id": "a", "query": "问题一", "positives": ["a.md"]}, 1),
        parse_case({"id": "b", "query": "问题二", "positives": ["b.md"]}, 2),
    ]
    hit_all = recall >= 1.0

    def _search(query: str, top_k: int) -> List[str]:
        if hit_all:
            return ["a.md"] if query == "问题一" else ["b.md"]
        return ["a.md"] if query == "问题一" else ["x.md"]

    report = run_evaluation(_search, cases, dataset_path="golden.jsonl")
    if latency_ms:
        report["summary"]["latency_ms"]["p95"] = latency_ms
    return report


class ReportStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_empty_dir_has_no_latest(self) -> None:
        self.assertIsNone(load_latest(self.dir))
        self.assertEqual(list_reports(self.dir), [])

    def test_missing_dir_does_not_raise(self) -> None:
        self.assertIsNone(load_latest(self.dir / "nope"))
        self.assertEqual(list_reports(self.dir / "nope"), [])

    def test_latest_json_is_preferred(self) -> None:
        save_report(_make_report(), self.dir / "report-20260101-000000.json")
        latest = load_latest(self.dir)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["schema"], REPORT_SCHEMA)

    def test_falls_back_to_newest_timestamped_file(self) -> None:
        save_report(_make_report(recall=0.5), self.dir / "report-20260101-000000.json")
        save_report(_make_report(recall=1.0), self.dir / "report-20260202-000000.json")
        (self.dir / "latest.json").unlink()
        latest = load_latest(self.dir)
        self.assertAlmostEqual(latest["summary"]["recall@5"], 1.0)

    def test_corrupt_latest_falls_back_instead_of_raising(self) -> None:
        save_report(_make_report(), self.dir / "report-20260101-000000.json")
        (self.dir / "latest.json").write_text("{ 坏掉的 json", encoding="utf-8")
        self.assertIsNotNone(load_latest(self.dir))

    def test_foreign_json_is_ignored(self) -> None:
        (self.dir / "report-20260101-000000.json").write_text(
            json.dumps({"schema": "something-else"}), encoding="utf-8"
        )
        self.assertIsNone(load_latest(self.dir))
        self.assertEqual(list_reports(self.dir), [])

    def test_history_is_newest_first_and_respects_limit(self) -> None:
        for stamp in ("20260101-000000", "20260202-000000", "20260303-000000"):
            save_report(_make_report(), self.dir / f"report-{stamp}.json")
        rows = list_reports(self.dir)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]["file"].startswith("report-20260303"))
        self.assertEqual(len(list_reports(self.dir, limit=2)), 2)

    def test_summarize_pulls_key_fields(self) -> None:
        row = summarize(_make_report())
        self.assertEqual(row["case_count"], 2)
        self.assertEqual(row["dataset_path"], "golden.jsonl")
        self.assertAlmostEqual(row["recall@5"], 1.0)
        self.assertIsNotNone(row["latency_p95_ms"])


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _kpi(self, payload: dict, key: str) -> dict:
        return next(item for item in payload["kpis"] if item["key"] == key)

    def test_no_report_shows_empty_state_not_fake_numbers(self) -> None:
        payload = build_dashboard(self.dir)
        self.assertFalse(payload["available"])
        self.assertIn("src.eval.cli", payload["hint"])
        self.assertIsNone(payload["latest"])
        for kpi in payload["kpis"]:
            self.assertIsNone(kpi["value"])
            self.assertEqual(kpi["status"], "unknown")
            self.assertEqual(kpi["display"], "—")

    def test_kpi_values_match_latest_report(self) -> None:
        report = _make_report(recall=1.0)
        save_report(report, self.dir / "report-20260101-000000.json")
        payload = build_dashboard(self.dir)
        self.assertTrue(payload["available"])
        self.assertAlmostEqual(
            self._kpi(payload, "recall@5")["value"], report["summary"]["recall@5"]
        )
        self.assertAlmostEqual(
            self._kpi(payload, "ndcg@10")["value"], report["summary"]["ndcg@10"]
        )

    def test_quality_line_pass_and_fail(self) -> None:
        save_report(_make_report(recall=1.0), self.dir / "report-20260101-000000.json")
        self.assertEqual(self._kpi(build_dashboard(self.dir), "recall@5")["status"], "pass")

        save_report(_make_report(recall=0.5), self.dir / "report-20260202-000000.json")
        self.assertEqual(self._kpi(build_dashboard(self.dir), "recall@5")["status"], "fail")

    def test_latency_target_is_smaller_is_better(self) -> None:
        save_report(
            _make_report(latency_ms=1200.0), self.dir / "report-20260101-000000.json"
        )
        kpi = self._kpi(build_dashboard(self.dir), "latency_p95_ms")
        self.assertEqual(kpi["direction"], "down")
        self.assertEqual(kpi["status"], "fail")
        self.assertIn("ms", kpi["display"])

    def test_history_is_exposed_for_trend(self) -> None:
        for stamp in ("20260101-000000", "20260202-000000"):
            save_report(_make_report(), self.dir / f"report-{stamp}.json")
        payload = build_dashboard(self.dir)
        self.assertEqual(len(payload["history"]), 2)


class _FakeHttp:
    """够用的 http 替身：只实现 handler 会碰的几个方法。"""

    def __init__(self, params: dict[str, list[str]] | None = None) -> None:
        self.params = params or {}
        self.responses: List[Tuple[int, Any]] = []

    def _parse_query_params(self) -> dict[str, list[str]]:
        return self.params

    def _ok(self, payload: Any, page_index: int = 1) -> None:
        self.responses.append((200, payload))

    def _bad_request(self, message: str, page_index: int = 1) -> None:
        self.responses.append((400, {"error": message}))


class MetricsHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("KB_EVAL_REPORT_DIR")
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["KB_EVAL_REPORT_DIR"] = self._tmpdir.name
        save_report(_make_report(), Path(self._tmpdir.name) / "report-20260101-000000.json")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        if self._old is None:
            os.environ.pop("KB_EVAL_REPORT_DIR", None)
        else:
            os.environ["KB_EVAL_REPORT_DIR"] = self._old

    def test_get_metrics_returns_dashboard(self) -> None:
        from src.api.handlers.metrics import handle_get_metrics

        http = _FakeHttp()
        self.assertTrue(handle_get_metrics(http, None, "/metrics"))
        code, payload = http.responses[0]
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertEqual(len(payload["kpis"]), 4)

    def test_get_reports_returns_history(self) -> None:
        from src.api.handlers.metrics import handle_get_metrics

        http = _FakeHttp()
        self.assertTrue(handle_get_metrics(http, None, "/metrics/reports"))
        _, payload = http.responses[0]
        self.assertEqual(len(payload["reports"]), 1)

    def test_bad_limit_is_rejected(self) -> None:
        from src.api.handlers.metrics import handle_get_metrics

        http = _FakeHttp({"limit": ["abc"]})
        self.assertTrue(handle_get_metrics(http, None, "/metrics"))
        self.assertEqual(http.responses[0][0], 400)

    def test_other_paths_are_not_claimed(self) -> None:
        from src.api.handlers.metrics import handle_get_metrics

        http = _FakeHttp()
        self.assertFalse(handle_get_metrics(http, None, "/stats"))
        self.assertEqual(http.responses, [])

    def test_dashboard_does_not_require_license(self) -> None:
        """商业包也不该因为没授权就看不到基础 KPI。"""
        from src.api.handlers.metrics import handle_get_metrics

        old_edition = os.environ.get("KB_EDITION")
        os.environ["KB_EDITION"] = "commercial"
        os.environ.pop("KB_LICENSE_DEV_BYPASS", None)
        try:
            http = _FakeHttp()
            handle_get_metrics(http, None, "/metrics")
            self.assertEqual(http.responses[0][0], 200)
        finally:
            if old_edition is None:
                os.environ.pop("KB_EDITION", None)
            else:
                os.environ["KB_EDITION"] = old_edition


if __name__ == "__main__":
    unittest.main()
