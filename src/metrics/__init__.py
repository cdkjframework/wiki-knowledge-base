"""
指标看板域（KB-11）。

把 KB-10 的评测报告整形成看板要的 KPI，社商共有，不依赖 License。
"""

from __future__ import annotations

from .dashboard import DEFAULT_TARGETS, build_dashboard, resolve_targets

__all__ = ["DEFAULT_TARGETS", "build_dashboard", "resolve_targets"]
