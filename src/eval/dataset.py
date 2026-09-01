"""
Golden 题集的格式、加载与校验。

沿用仓库里 `eval_dataset.example.jsonl` / `tune_threshold.py` 已有的 JSONL 约定，
老题集不用改就能继续跑；新增 id / tags 只是为了报告里能按条追溯和按域切片。

一行一条，UTF-8，`#` 开头视为注释：

    {"id": "kb-001", "query": "如何升级", "positives": ["升级迁移指南.md"], "tags": ["运维"]}

positives 支持这些等价写法（兼容旧题集）：
positives / positive_filenames / expected_filenames（数组）、
expected_filename / filename（字符串）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

_LIST_FIELDS: Tuple[str, ...] = ("positives", "positive_filenames", "expected_filenames")
_SCALAR_FIELDS: Tuple[str, ...] = ("expected_filename", "filename")


@dataclass(frozen=True)
class GoldenCase:
    """一道评测题：问题 + 应该命中的文档。"""

    id: str
    query: str
    positives: Tuple[str, ...]
    tags: Tuple[str, ...] = field(default=())
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "positives": list(self.positives),
            "tags": list(self.tags),
            "note": self.note,
        }


class DatasetError(ValueError):
    """题集格式问题；带行号，方便直接定位到哪一行写错了。"""


def default_dataset_path(root: Path | None = None) -> Path:
    """默认题集位置；`KB_EVAL_DATASET` 可覆盖，方便各自指向自己的语料题集。"""
    env = str(os.getenv("KB_EVAL_DATASET", "")).strip()
    if env:
        return Path(env).expanduser()
    base = root if root is not None else _project_root()
    return base / "conf" / "eval" / "golden-default.jsonl"


def _project_root() -> Path:
    from src.shared.config_paths import resolve_project_root

    return resolve_project_root()


def parse_case(obj: Dict[str, Any], lineno: int, fallback_id: str = "") -> GoldenCase:
    """把一行 JSON 解析成题目；缺 query 或缺答案都直接报错，不静默跳过。"""
    if not isinstance(obj, dict):
        raise DatasetError(f"第 {lineno} 行不是 JSON 对象")

    query = str(obj.get("query") or "").strip()
    if not query:
        raise DatasetError(f"第 {lineno} 行缺少 query")

    positives: List[str] = []
    for key in _LIST_FIELDS:
        value = obj.get(key)
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text and text not in positives:
                    positives.append(text)
    for key in _SCALAR_FIELDS:
        value = obj.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in positives:
            positives.append(value.strip())

    if not positives:
        raise DatasetError(
            f"第 {lineno} 行缺少标准答案；请填 positives / expected_filename 之一"
        )

    raw_tags = obj.get("tags")
    tags: Tuple[str, ...] = ()
    if isinstance(raw_tags, list):
        tags = tuple(str(t).strip() for t in raw_tags if str(t).strip())
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = (raw_tags.strip(),)

    case_id = str(obj.get("id") or "").strip() or fallback_id or f"case-{lineno:04d}"
    return GoldenCase(
        id=case_id,
        query=query,
        positives=tuple(positives),
        tags=tags,
        note=str(obj.get("note") or "").strip(),
    )


def load_dataset(path: str | Path | None = None) -> List[GoldenCase]:
    """
    读取 JSONL 题集。

    题号重复会直接报错：跑分报告按 id 追溯，重号会让两次结果对不上。
    """
    target = Path(path) if path is not None else default_dataset_path()
    if not target.exists():
        raise FileNotFoundError(f"题集不存在：{target}")

    cases: List[GoldenCase] = []
    seen_ids: Dict[str, int] = {}
    with target.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"第 {lineno} 行 JSON 解析失败：{exc}") from exc
            case = parse_case(obj, lineno)
            if case.id in seen_ids:
                raise DatasetError(
                    f"第 {lineno} 行题号重复：{case.id}（首次出现在第 {seen_ids[case.id]} 行）"
                )
            seen_ids[case.id] = lineno
            cases.append(case)

    if not cases:
        raise DatasetError(f"题集为空：{target}")
    return cases
