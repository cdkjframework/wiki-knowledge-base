"""
把评测报告整形成看板 KPI。

看板只做「读 + 摆」，不自己算指标：数值一律来自 KB-10 报告，
这样「看板和最近一次跑分对得上」是结构保证的，不是靠两边算法碰巧一致。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..eval.reports import list_reports, load_latest, summarize

# 验收线来自 KB-01 混合检索的质量线；越小越好的指标写 direction=down
DEFAULT_TARGETS: Dict[str, Dict[str, Any]] = {
    "recall@5": {"label": "Recall@5", "target": 0.85, "direction": "up", "unit": ""},
    "recall@3": {"label": "Recall@3", "target": 0.75, "direction": "up", "unit": ""},
    "ndcg@10": {"label": "NDCG@10", "target": 0.70, "direction": "up", "unit": ""},
    "latency_p95_ms": {"label": "检索 p95", "target": 300.0, "direction": "down", "unit": "ms"},
}

_CORE_KPIS = ("recall@5", "recall@3", "ndcg@10", "latency_p95_ms")

_RUN_HINT = "尚未跑过评测。执行 python -m src.eval.cli 生成第一份报告后刷新本页。"


def resolve_targets() -> Dict[str, Dict[str, Any]]:
    """
    取验收线，允许 conf 里覆盖。

    不同语料的合理线差很多，写死会让看板一直标红，所以留了 `metrics.targets` 这个口子。
    """
    targets = {key: dict(value) for key, value in DEFAULT_TARGETS.items()}
    try:
        from ..shared.config_paths import load_project_config

        cfg = load_project_config() or {}
    except Exception:
        return targets

    overrides = ((cfg.get("metrics") or {}).get("targets")) or {}
    if not isinstance(overrides, dict):
        return targets
    for key, raw in overrides.items():
        if key not in targets:
            continue
        try:
            targets[key]["target"] = float(raw)
        except (TypeError, ValueError):
            continue
    return targets


def _format_value(key: str, value: Any, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "ms":
        return f"{float(value):.0f} ms"
    return f"{float(value):.3f}"


def _format_target(target: float, direction: str, unit: str) -> str:
    symbol = "≥" if direction == "up" else "≤"
    if unit == "ms":
        return f"{symbol} {target:.0f} ms"
    return f"{symbol} {target:.2f}"


def _judge(value: Any, target: float, direction: str) -> str:
    """没有数据就说 unknown，别拿 0 当「不达标」吓人。"""
    if value is None:
        return "unknown"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if direction == "down":
        return "pass" if numeric <= target else "fail"
    return "pass" if numeric >= target else "fail"


def _build_kpis(row: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    targets = resolve_targets()
    kpis: List[Dict[str, Any]] = []
    for key in _CORE_KPIS:
        spec = targets[key]
        value = row.get(key) if row else None
        unit = str(spec.get("unit") or "")
        target = float(spec["target"])
        direction = str(spec["direction"])
        kpis.append(
            {
                "key": key,
                "label": str(spec["label"]),
                "value": value,
                "display": _format_value(key, value, unit),
                "target": target,
                "target_display": _format_target(target, direction, unit),
                "direction": direction,
                "unit": unit,
                "status": _judge(value, target, direction),
            }
        )
    return kpis


def build_dashboard(
    report_dir: Path | None = None, history_limit: int = 20
) -> Dict[str, Any]:
    """
    组装看板数据。

    没跑过评测时不编数：`available=False` + 一句怎么跑的提示，
    前端照实显示「暂无数据」，避免又变成占位假数。
    """
    latest = load_latest(report_dir)
    row = summarize(latest) if latest else None
    history = list_reports(report_dir, limit=history_limit)

    payload: Dict[str, Any] = {
        "available": latest is not None,
        "kpis": _build_kpis(row),
        "latest": row,
        "history": history,
    }
    if latest is None:
        payload["hint"] = _RUN_HINT
    return payload
