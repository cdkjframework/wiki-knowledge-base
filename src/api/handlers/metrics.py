"""
指标看板 HTTP 路由（KB-11）：GET /api/metrics、GET /api/metrics/reports。

社商共有，**不做 License 门控**——基础质量 KPI 是两个版本都该看得见的。
"""

from __future__ import annotations

from typing import Any


def _load_dashboard_mod():
    try:
        from ...metrics import dashboard  # type: ignore
    except ImportError:
        from metrics import dashboard  # type: ignore
    return dashboard


def _load_reports_mod():
    try:
        from ...eval import reports  # type: ignore
    except ImportError:
        from eval import reports  # type: ignore
    return reports


def _limit_from_params(http: Any, default: int) -> int | None:
    """解析 ?limit=；非法值直接 400，别默默按默认值返回让人以为数据就这么多。"""
    params = http._parse_query_params()
    raw = params.get("limit") or []
    if not raw:
        return default
    try:
        value = int(raw[-1])
    except (TypeError, ValueError):
        http._bad_request("limit 必须是整数")
        return None
    return max(1, min(200, value))


def handle_get_metrics(http: Any, api: Any, path: str) -> bool:
    """GET /metrics：看板 KPI + 最近一次评测 + 历史列表。"""
    if path == "/metrics":
        limit = _limit_from_params(http, 20)
        if limit is None:
            return True
        dashboard = _load_dashboard_mod()
        http._ok({"ok": True, **dashboard.build_dashboard(history_limit=limit)})
        return True

    if path == "/metrics/reports":
        limit = _limit_from_params(http, 50)
        if limit is None:
            return True
        reports = _load_reports_mod()
        http._ok({"ok": True, "reports": reports.list_reports(limit=limit)})
        return True

    return False
