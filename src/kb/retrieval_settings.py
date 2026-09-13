"""
KB-20：检索与固定长度分片参数的校验 / 快照 / 写入配置字典。

热更新本身由 API 层改 KnowledgeBase 运行时属性；这里只负责「数合不合法」和「怎么落盘」。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping


# 面板可调范围：太野的数会把召回或切分搞崩，拦在入口
BOUNDS = {
    "default_k": (1, 50),
    "max_search_results": (1, 100),
    "min_source_similarity": (0.0, 1.0),
    "chunk_size": (100, 8000),
    "chunk_overlap": (0, 7999),
}

SETTING_KEYS = (
    "default_k",
    "max_search_results",
    "min_source_similarity",
    "chunk_size",
    "chunk_overlap",
)


def snapshot_from_runtime(kb: Any, search_cfg: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """从当前进程生效值读一份面板快照。"""
    cfg = search_cfg if isinstance(search_cfg, Mapping) else {}
    try:
        min_sim = float(cfg.get("min_source_similarity", 0.0) or 0.0)
    except (TypeError, ValueError):
        min_sim = 0.0
    min_sim = max(0.0, min(1.0, min_sim))

    return {
        "default_k": int(getattr(kb, "default_k", 5) or 5),
        "max_search_results": int(getattr(kb, "max_search_results", 10) or 10),
        "min_source_similarity": min_sim,
        "chunk_size": int(getattr(kb, "chunk_size", 800) or 800),
        "chunk_overlap": int(getattr(kb, "chunk_overlap", 120) or 0),
        "chunking_strategy": "fixed",
        "notes": {
            "search": "检索参数保存后立即生效，无需重启服务。",
            "chunk": "分片参数仅对新导入或「重建分片」生效；旧文档不会自动重切。",
            "threshold": "min_source_similarity=0 表示关闭硬阈值过滤（推荐做对比实验时先关掉）。",
        },
    }


def _as_int(name: str, raw: Any, *, lo: int, hi: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < lo or value > hi:
        raise ValueError(f"{name} 须在 {lo}～{hi} 之间")
    return value


def _as_float(name: str, raw: Any, *, lo: float, hi: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if value < lo or value > hi:
        raise ValueError(f"{name} 须在 {lo}～{hi} 之间")
    return value


def normalize_settings(
    payload: Mapping[str, Any] | None,
    *,
    current: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    合并请求体与当前值，校验后返回可落盘/可热更新的字典。
    未传的字段保持 current（或合理默认）。
    """
    base = {
        "default_k": 5,
        "max_search_results": 10,
        "min_source_similarity": 0.0,
        "chunk_size": 800,
        "chunk_overlap": 120,
    }
    if isinstance(current, Mapping):
        for key in SETTING_KEYS:
            if key in current and current[key] is not None:
                base[key] = current[key]

    data = payload if isinstance(payload, Mapping) else {}
    merged = dict(base)
    for key in SETTING_KEYS:
        if key in data and data[key] is not None:
            merged[key] = data[key]

    dk = _as_int("default_k", merged["default_k"], lo=BOUNDS["default_k"][0], hi=BOUNDS["default_k"][1])
    mx = _as_int(
        "max_search_results",
        merged["max_search_results"],
        lo=BOUNDS["max_search_results"][0],
        hi=BOUNDS["max_search_results"][1],
    )
    if mx < dk:
        raise ValueError("max_search_results 不能小于 default_k")

    sim = _as_float(
        "min_source_similarity",
        merged["min_source_similarity"],
        lo=BOUNDS["min_source_similarity"][0],
        hi=BOUNDS["min_source_similarity"][1],
    )
    size = _as_int("chunk_size", merged["chunk_size"], lo=BOUNDS["chunk_size"][0], hi=BOUNDS["chunk_size"][1])
    overlap = _as_int(
        "chunk_overlap",
        merged["chunk_overlap"],
        lo=BOUNDS["chunk_overlap"][0],
        hi=min(BOUNDS["chunk_overlap"][1], size - 1),
    )

    return {
        "default_k": dk,
        "max_search_results": mx,
        "min_source_similarity": sim,
        "chunk_size": size,
        "chunk_overlap": overlap,
    }


def apply_settings_to_config(config: MutableMapping[str, Any], settings: Mapping[str, Any]) -> None:
    """把归一化后的设置写进 config 字典（原地修改）。"""
    search = config.get("search")
    if not isinstance(search, dict):
        search = {}
        config["search"] = search
    search["default_k"] = int(settings["default_k"])
    search["max_search_results"] = int(settings["max_search_results"])
    search["min_source_similarity"] = float(settings["min_source_similarity"])

    kb_cfg = config.get("knowledge_base")
    if not isinstance(kb_cfg, dict):
        kb_cfg = {}
        config["knowledge_base"] = kb_cfg
    chunking = kb_cfg.get("chunking")
    if not isinstance(chunking, dict):
        chunking = {}
        kb_cfg["chunking"] = chunking
    chunking["size"] = int(settings["chunk_size"])
    chunking["overlap"] = int(settings["chunk_overlap"])


def apply_settings_to_runtime(kb: Any, search_cfg: MutableMapping[str, Any], settings: Mapping[str, Any]) -> None:
    """改进程内生效值，免重启。"""
    kb.default_k = int(settings["default_k"])
    kb.max_search_results = int(settings["max_search_results"])
    kb.chunk_size = int(settings["chunk_size"])
    kb.chunk_overlap = int(settings["chunk_overlap"])
    search_cfg["default_k"] = int(settings["default_k"])
    search_cfg["max_search_results"] = int(settings["max_search_results"])
    search_cfg["min_source_similarity"] = float(settings["min_source_similarity"])
