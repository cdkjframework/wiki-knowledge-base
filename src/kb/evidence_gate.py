"""
证据门槛：决定一条检索候选能不能当「知识来源」给用户看、喂给生成模型。

为什么单独一层：
- 综合分不是正确率，BM25 相对分更不是；只看 min_source_similarity 挡不住泛词误召回。
- API 那边有「阈值检索为空就无阈值重试」的回退，门槛必须放在回退之后，不能被绕过。
- 评测跑分也要走同一套判定，否则反例题的误召回率量出来没有意义。

判定只依赖语义证据（向量余弦、重排概率），BM25 只负责把候选捞上来，不单独放行。
数值阈值都是保守初值，按 conf/eval 正反例校准后再改默认值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .query_terms import entity_matched, extract_entities, normalize_aliases

STATUS_SUFFICIENT = "sufficient"
STATUS_INSUFFICIENT = "insufficient"


def _as_float(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value != value:  # NaN
        return default
    return max(0.0, min(1.0, value))


def _as_bool(raw: Any, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    if isinstance(raw, (int, float)):
        return bool(raw)
    return default


@dataclass(frozen=True)
class EvidencePolicy:
    """门槛参数；来自 knowledge_base.retrieval.evidence，缺省即下面这些保守值。"""

    enabled: bool = True
    # 重排概率（0～1，已按后端换算过）达到它才算「重排认为相关」
    min_rerank_probability: float = 0.5
    # 没有重排可用时，向量余弦至少要到这里
    min_vector_similarity: float = 0.5
    # 重排说不相关、但向量极高时允许放行；防止重排模型偶发失手把真答案全拒掉
    strong_vector_similarity: float = 0.75
    # 查询带实体（PMP、KB-10）而证据里没出现实体 / 别名时，重排要更有把握才放行
    entity_miss_rerank_probability: float = 0.8
    aliases: Mapping[str, Sequence[str]] = field(default_factory=dict)
    extra_generic_terms: Tuple[str, ...] = ()

    @classmethod
    def from_config(
        cls,
        cfg: Mapping[str, Any] | None,
        *,
        aliases: Mapping[str, Sequence[str]] | None = None,
    ) -> "EvidencePolicy":
        data = cfg if isinstance(cfg, Mapping) else {}
        base = cls()
        merged_aliases = dict(normalize_aliases(aliases))
        for key, values in normalize_aliases(data.get("aliases")).items():
            merged_aliases.setdefault(key, [])
            for value in values:
                if value not in merged_aliases[key]:
                    merged_aliases[key].append(value)
        extra = data.get("extra_generic_terms")
        extra_terms: Tuple[str, ...] = ()
        if isinstance(extra, (list, tuple)):
            extra_terms = tuple(str(x).strip() for x in extra if str(x).strip())
        return cls(
            enabled=_as_bool(data.get("enabled"), base.enabled),
            min_rerank_probability=_as_float(
                data.get("min_rerank_probability"), base.min_rerank_probability
            ),
            min_vector_similarity=_as_float(
                data.get("min_vector_similarity"), base.min_vector_similarity
            ),
            strong_vector_similarity=_as_float(
                data.get("strong_vector_similarity"), base.strong_vector_similarity
            ),
            entity_miss_rerank_probability=_as_float(
                data.get("entity_miss_rerank_probability"),
                base.entity_miss_rerank_probability,
            ),
            aliases=merged_aliases,
            extra_generic_terms=extra_terms,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "min_rerank_probability": self.min_rerank_probability,
            "min_vector_similarity": self.min_vector_similarity,
            "strong_vector_similarity": self.strong_vector_similarity,
            "entity_miss_rerank_probability": self.entity_miss_rerank_probability,
            "alias_count": len(self.aliases or {}),
            "extra_generic_terms": list(self.extra_generic_terms),
        }


@dataclass
class EvidenceDecision:
    passed: List[Dict[str, Any]]
    rejected: List[Dict[str, Any]]
    entities: List[str]

    @property
    def status(self) -> str:
        return STATUS_SUFFICIENT if self.passed else STATUS_INSUFFICIENT


def _optional_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if value != value else value


def _rerank_view(item: Mapping[str, Any]) -> Tuple[bool, float | None]:
    """重排是否可用 + 概率。老明细没有 rerank_status 时，有分就当可用。"""
    prob = _optional_float(item.get("rerank_similarity"))
    status = str(item.get("rerank_status") or "").strip().lower()
    if not status:
        status = "ok" if prob is not None else "disabled"
    return status == "ok" and prob is not None, prob


def _judge(
    item: Mapping[str, Any],
    policy: EvidencePolicy,
    entities: Sequence[str],
) -> Tuple[bool, str, bool | None]:
    """返回 (是否放行, 依据或拒绝原因, 实体是否命中)。"""
    vec = _optional_float(item.get("vector_similarity", item.get("embed_similarity")))
    rr_ok, rr = _rerank_view(item)

    entity_hit: bool | None = None
    if entities:
        haystacks = [str(item.get("text") or ""), str(item.get("filename") or "")]
        entity_hit = any(entity_matched(e, haystacks, policy.aliases) for e in entities)

    if entities and not entity_hit:
        if rr_ok and rr is not None and rr >= policy.entity_miss_rerank_probability:
            return True, "rerank_strict", entity_hit
        if not rr_ok and vec is not None and vec >= policy.strong_vector_similarity:
            return True, "vector_strict", entity_hit
        return False, "查询实体未出现在证据中，且语义分不足", entity_hit

    if rr_ok and rr is not None:
        if rr >= policy.min_rerank_probability:
            return True, "rerank", entity_hit
        if vec is not None and vec >= policy.strong_vector_similarity:
            return True, "vector_strong", entity_hit
        return False, "重排判定不相关", entity_hit

    if vec is None:
        return False, "缺少语义证据（仅字面命中且重排不可用）", entity_hit
    if vec >= policy.min_vector_similarity:
        return True, "vector", entity_hit
    return False, "向量相似度不足", entity_hit


def evaluate_evidence(
    query: str,
    items: Sequence[Dict[str, Any]],
    policy: EvidencePolicy | None = None,
) -> EvidenceDecision:
    """
    逐条判定候选；放行的条目会带上 evidence 字段（依据、实体命中），原字典就地补充。

    items 需要 filename / text，以及检索明细里的 vector_similarity、
    rerank_similarity、rerank_status（缺了按「没有这项证据」处理）。
    """
    pol = policy or EvidencePolicy()
    entities = extract_entities(query)
    passed: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for item in items:
        if not pol.enabled:
            item["evidence"] = {"passed": True, "basis": "disabled", "entity_matched": None}
            passed.append(item)
            continue
        ok, reason, entity_hit = _judge(item, pol, entities)
        if ok:
            item["evidence"] = {"passed": True, "basis": reason, "entity_matched": entity_hit}
            passed.append(item)
        else:
            item["evidence"] = {"passed": False, "reason": reason, "entity_matched": entity_hit}
            rejected.append(item)
    return EvidenceDecision(passed=passed, rejected=rejected, entities=entities)
