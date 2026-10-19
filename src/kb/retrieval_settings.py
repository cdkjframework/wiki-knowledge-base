"""
KB-20：检索与固定长度分片参数的校验 / 快照 / 写入配置字典。

热更新本身由 API 层改 KnowledgeBase 运行时属性；这里只负责「数合不合法」和「怎么落盘」。
KB-01：补充 hybrid_enabled / rrf_k，控制 BM25∪向量融合。
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
    "rrf_k": (1, 200),
    "max_rerank_candidates": (1, 100),
}

SETTING_KEYS = (
    "default_k",
    "max_search_results",
    "min_source_similarity",
    "chunk_size",
    "chunk_overlap",
    "hybrid_enabled",
    "rrf_k",
    "max_rerank_candidates",
)


def snapshot_from_runtime(kb: Any, search_cfg: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """从当前进程生效值读一份面板快照。"""
    cfg = search_cfg if isinstance(search_cfg, Mapping) else {}
    try:
        min_sim = float(cfg.get("min_source_similarity", 0.0) or 0.0)
    except (TypeError, ValueError):
        min_sim = 0.0
    min_sim = max(0.0, min(1.0, min_sim))

    hybrid = getattr(kb, "hybrid_enabled", None)
    if hybrid is None:
        hybrid = cfg.get("hybrid_enabled", True)
    hybrid = bool(hybrid)

    try:
        rrf_k = int(getattr(kb, "rrf_k", cfg.get("rrf_k", 60)) or 60)
    except (TypeError, ValueError):
        rrf_k = 60
    rrf_k = max(BOUNDS["rrf_k"][0], min(BOUNDS["rrf_k"][1], rrf_k))

    try:
        max_rr = int(
            getattr(kb, "max_rerank_candidates", cfg.get("max_rerank_candidates", 8)) or 8
        )
    except (TypeError, ValueError):
        max_rr = 8
    max_rr = max(
        BOUNDS["max_rerank_candidates"][0],
        min(BOUNDS["max_rerank_candidates"][1], max_rr),
    )

    return {
        "default_k": int(getattr(kb, "default_k", 5) or 5),
        "max_search_results": int(getattr(kb, "max_search_results", 10) or 10),
        "min_source_similarity": min_sim,
        "chunk_size": int(getattr(kb, "chunk_size", 800) or 800),
        "chunk_overlap": int(getattr(kb, "chunk_overlap", 120) or 0),
        "hybrid_enabled": hybrid,
        "rrf_k": rrf_k,
        "max_rerank_candidates": max_rr,
        "chunking_strategy": "fixed",
        "notes": {
            "search": "检索参数保存后立即生效，无需重启服务。",
            "chunk": "分片参数仅对新导入或「重建分片」生效；旧文档不会自动重切。",
            "threshold": "候选过滤线（min_source_similarity）保存在数据库；0 表示关闭。它比的是内部排序分，不是正确率；候选最终能否作为来源由证据门槛（knowledge_base.retrieval.evidence）决定。",
            "persist": "检索与分片参数优先写入数据库 kb_app_settings，重启后仍生效；无库时回退 conf/config.json。",
            "hybrid": "hybrid_enabled=true 时走 BM25∪向量 RRF 融合后再重排；关闭则仅向量+重排。单通道失败会自动降级到另一路。",
            "rerank": "max_rerank_candidates 限制送入交叉编码器的候选数，显著影响 CPU 延迟；检索 p95 验收测混合召回（可用 --no-rerank）。",
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


def _as_bool(name: str, raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{name} 必须是布尔值")


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
        "min_source_similarity": 0.6,
        "chunk_size": 800,
        "chunk_overlap": 120,
        "hybrid_enabled": True,
        "rrf_k": 60,
        "max_rerank_candidates": 8,
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
    hybrid = _as_bool("hybrid_enabled", merged["hybrid_enabled"])
    rrf_k = _as_int("rrf_k", merged["rrf_k"], lo=BOUNDS["rrf_k"][0], hi=BOUNDS["rrf_k"][1])
    max_rr = _as_int(
        "max_rerank_candidates",
        merged["max_rerank_candidates"],
        lo=BOUNDS["max_rerank_candidates"][0],
        hi=BOUNDS["max_rerank_candidates"][1],
    )

    return {
        "default_k": dk,
        "max_search_results": mx,
        "min_source_similarity": sim,
        "chunk_size": size,
        "chunk_overlap": overlap,
        "hybrid_enabled": hybrid,
        "rrf_k": rrf_k,
        "max_rerank_candidates": max_rr,
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
    search["hybrid_enabled"] = bool(settings["hybrid_enabled"])
    search["rrf_k"] = int(settings["rrf_k"])
    search["max_rerank_candidates"] = int(settings["max_rerank_candidates"])

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

    retrieval = kb_cfg.get("retrieval")
    if not isinstance(retrieval, dict):
        retrieval = {}
        kb_cfg["retrieval"] = retrieval
    retrieval["hybrid_enabled"] = bool(settings["hybrid_enabled"])
    retrieval["rrf_k"] = int(settings["rrf_k"])
    retrieval["max_rerank_candidates"] = int(settings["max_rerank_candidates"])


def apply_settings_to_runtime(kb: Any, search_cfg: MutableMapping[str, Any], settings: Mapping[str, Any]) -> None:
    """改进程内生效值，免重启。"""
    kb.default_k = int(settings["default_k"])
    kb.max_search_results = int(settings["max_search_results"])
    kb.chunk_size = int(settings["chunk_size"])
    kb.chunk_overlap = int(settings["chunk_overlap"])
    kb.hybrid_enabled = bool(settings["hybrid_enabled"])
    kb.rrf_k = int(settings["rrf_k"])
    kb.max_rerank_candidates = int(settings["max_rerank_candidates"])
    search_cfg["default_k"] = int(settings["default_k"])
    search_cfg["max_search_results"] = int(settings["max_search_results"])
    search_cfg["min_source_similarity"] = float(settings["min_source_similarity"])
    search_cfg["hybrid_enabled"] = bool(settings["hybrid_enabled"])
    search_cfg["rrf_k"] = int(settings["rrf_k"])
    search_cfg["max_rerank_candidates"] = int(settings["max_rerank_candidates"])
