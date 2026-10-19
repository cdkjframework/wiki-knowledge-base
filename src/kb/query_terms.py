"""
查询词治理：泛词剔除、实体（缩写 / 编号）识别、实体别名。

BM25 查询端和证据门槛共用这一套规则，免得两边各写各的、口径越改越歪。
只动「查询怎么切」，索引侧的 tokenize 不变，所以不需要重建索引。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

logger = logging.getLogger(__name__)

# 只表达「我想查点东西」的词，单独命中不说明文档和问题相关。
# 故意列得很克制：像「文档」「流程」「配置」这种在业务问句里常带实义的词不放进来。
DEFAULT_GENERIC_TERMS: Tuple[str, ...] = (
    "有哪些",
    "是什么",
    "什么",
    "哪些",
    "内容",
    "资料",
    "介绍",
    "相关",
    "信息",
    "详情",
    "怎么",
    "如何",
    "请问",
    "关于",
    "一下",
)

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
# 拉丁 / 数字片段；允许中间带 - . _（KB-10、v1.1.3、ISO_9001）
_LATIN_RUN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.\-]*[A-Za-z0-9])?")
_INDEX_LATIN_WORD = re.compile(r"[A-Za-z0-9_]+")
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"[0-9]")


def _generic_list(extra: Iterable[str] | None) -> List[str]:
    terms = list(DEFAULT_GENERIC_TERMS)
    for item in extra or ():
        text = str(item or "").strip()
        if text and text not in terms:
            terms.append(text)
    # 长词先剥，免得「是什么」先被「什么」切成半截
    return sorted(terms, key=len, reverse=True)


def is_entity_token(raw: str) -> bool:
    """
    判断一个拉丁片段是不是「明确实体」。

    认：全大写缩写（PMP、RBAC）、字母数字混排（ISO9001、v1.1）、带连字符的编号（KB-10）。
    不认：普通小写英文单词（license、hello），它们更像描述词，拿来卡门槛会误杀。
    """
    text = str(raw or "").strip()
    if len(text) < 2 or not _HAS_LETTER.search(text):
        return False
    if _HAS_DIGIT.search(text):
        return True
    if "-" in text or "_" in text:
        return True
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 2 and all(ch.isupper() for ch in letters)


def extract_entities(query: str) -> List[str]:
    """按出现顺序返回查询里的实体（小写、去重）。"""
    out: List[str] = []
    for match in _LATIN_RUN.finditer(str(query or "")):
        token = match.group(0)
        if is_entity_token(token):
            low = token.lower()
            if low not in out:
                out.append(low)
    return out


def strip_generic_terms(query: str, extra_generic: Iterable[str] | None = None) -> str:
    """把泛词替换成空格，让后面的双字切分不会跨过被剥掉的位置。"""
    text = str(query or "")
    for term in _generic_list(extra_generic):
        if term:
            text = text.replace(term, " ")
    return text


def tokenize_query(
    query: str,
    *,
    extra_generic: Iterable[str] | None = None,
) -> List[str]:
    """
    BM25 查询端切词（索引端仍用 bm25_index.tokenize）。

    - 先剥泛词：`PMP内容` 不再拆出 `内` / `容` / `内容`。
    - 拉丁片段按词保留（小写）。
    - 中文按「剥完后的每一段」切字 + 双字，双字不跨段。
    - 查询里有实体时丢掉中文单字：单字太泛，会让 `内`、`容` 顶替实体去捞无关文档。
    - 剥完什么都不剩就返回空，交给向量通道独立召回。
    """
    raw = str(query or "").strip()
    if not raw:
        return []
    has_entity = bool(extract_entities(raw))
    stripped = strip_generic_terms(raw, extra_generic).lower()

    # 拉丁词元必须和索引端 tokenize 的切法一致（KB-10 → kb / 10），否则永远对不上
    tokens: List[str] = list(_INDEX_LATIN_WORD.findall(stripped))
    for run in _CJK_RUN.findall(stripped):
        if not has_entity:
            tokens.extend(run)
        if len(run) >= 2:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return list(dict.fromkeys(tokens))


def normalize_aliases(raw: Mapping[str, Sequence[str]] | None) -> Dict[str, List[str]]:
    """别名表统一成 {实体小写: [别名小写...]}，别名双向都认。"""
    out: Dict[str, List[str]] = {}
    if not isinstance(raw, Mapping):
        return out
    for key, values in raw.items():
        name = str(key or "").strip().lower()
        if not name:
            continue
        items: List[str] = []
        if isinstance(values, (list, tuple)):
            for value in values:
                text = str(value or "").strip().lower()
                if text and text != name and text not in items:
                    items.append(text)
        if items:
            out.setdefault(name, [])
            for text in items:
                if text not in out[name]:
                    out[name].append(text)
    return out


def load_aliases_file(path: str | Path | None) -> Dict[str, List[str]]:
    """读别名 JSON；文件缺失或写坏都当空表，别让一个配置文件拖垮检索。"""
    if not path:
        return {}
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("实体别名文件读取失败，按空表处理: %s (%s)", target, exc)
        return {}
    if isinstance(data, Mapping) and isinstance(data.get("aliases"), Mapping):
        data = data["aliases"]
    return normalize_aliases(data if isinstance(data, Mapping) else None)


def entity_variants(entity: str, aliases: Mapping[str, Sequence[str]] | None = None) -> List[str]:
    """实体本身 + 已配置的别名（小写）。"""
    name = str(entity or "").strip().lower()
    if not name:
        return []
    variants = [name]
    for alias in (aliases or {}).get(name, []) or []:
        if alias not in variants:
            variants.append(alias)
    return variants


def entity_matched(
    entity: str,
    haystacks: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> bool:
    """实体或其任一别名是否出现在正文 / 文件名里（大小写不敏感）。"""
    variants = entity_variants(entity, aliases)
    if not variants:
        return False
    lowered = [str(h or "").lower() for h in haystacks]
    for variant in variants:
        for text in lowered:
            if variant and variant in text:
                return True
    return False
