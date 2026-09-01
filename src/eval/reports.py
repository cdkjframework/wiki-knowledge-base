"""
评测报告的读取与历史列表（KB-11 看板的数据来源）。

跑分那头只管把 JSON 写进报告目录，这里只管读，两边不互相依赖，
所以看板即使在没装模型的机器上也能把最近一次结果显示出来。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .runner import REPORT_SCHEMA, default_report_dir

LATEST_NAME = "latest.json"
_REPORT_GLOB = "report-*.json"


def _read_json(path: Path) -> Dict[str, Any] | None:
    """读坏了就当没有：看板不该因为一个残缺文件整页报错。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_report(data: Dict[str, Any]) -> bool:
    return str(data.get("schema") or "") == REPORT_SCHEMA


def summarize(data: Dict[str, Any], path: Path | None = None) -> Dict[str, Any]:
    """把整份报告压成列表行要用的摘要，避免把上百题的明细传给前端。"""
    summary = data.get("summary") or {}
    dataset = data.get("dataset") or {}
    config = data.get("config") or {}
    latency = summary.get("latency_ms") or {}
    return {
        "file": path.name if path is not None else "",
        "generated_at": data.get("generated_at") or "",
        "dataset_path": dataset.get("path") or "",
        "case_count": summary.get("case_count") or dataset.get("case_count") or 0,
        "failed_count": summary.get("failed_count") or 0,
        "recall@3": summary.get("recall@3"),
        "recall@5": summary.get("recall@5"),
        "ndcg@10": summary.get("ndcg@10"),
        "mrr": summary.get("mrr"),
        "latency_p95_ms": latency.get("p95"),
        "total_seconds": summary.get("total_seconds"),
        "top_k": config.get("top_k"),
    }


def load_latest(report_dir: Path | None = None) -> Dict[str, Any] | None:
    """
    读最近一次报告。

    优先认 `latest.json`；它缺失或损坏时回退到时间戳文件里最新的一份，
    这样手工挪过文件的目录也还能用。
    """
    base = report_dir if report_dir is not None else default_report_dir()
    latest = base / LATEST_NAME
    if latest.exists():
        data = _read_json(latest)
        if data is not None and _is_report(data):
            return data

    for path in _sorted_report_files(base):
        data = _read_json(path)
        if data is not None and _is_report(data):
            return data
    return None


def _sorted_report_files(base: Path) -> List[Path]:
    """按文件名倒序；报告名带时间戳，字典序就是时间序。"""
    if not base.is_dir():
        return []
    return sorted(base.glob(_REPORT_GLOB), key=lambda p: p.name, reverse=True)


def list_reports(report_dir: Path | None = None, limit: int = 20) -> List[Dict[str, Any]]:
    """列出历史报告摘要，最新在前。"""
    base = report_dir if report_dir is not None else default_report_dir()
    rows: List[Dict[str, Any]] = []
    for path in _sorted_report_files(base):
        if limit > 0 and len(rows) >= limit:
            break
        data = _read_json(path)
        if data is None or not _is_report(data):
            continue
        rows.append(summarize(data, path))
    return rows
