"""
知识库文档域门面：对 KnowledgeBase 的文档/分片操做做薄封装。

后续 http_server 中的 list/add/remove 将逐步改为调用本模块。
"""

from __future__ import annotations

from typing import Any, Dict, List


def list_documents(kb: Any, *, is_internal_filename=None) -> Dict[str, Any]:
    """
    列出公开文档。

    Args:
        kb: KnowledgeBase 实例
        is_internal_filename: 可选过滤函数，返回 True 表示内部文档需排除
    """
    docs: List[Dict[str, Any]] = list(kb.list_documents())
    if is_internal_filename is not None:
        docs = [d for d in docs if not is_internal_filename(d.get("filename"))]
    return {"ok": True, "count": len(docs), "documents": docs}


def list_chunks(
    kb: Any,
    *,
    page_index: int = 1,
    page_size: int = 20,
    filename: str | None = None,
    query: str | None = None,
    is_internal_filename=None,
) -> Dict[str, Any]:
    """分页列出分片。"""
    if is_internal_filename is not None and is_internal_filename(filename):
        return {"ok": True, "count": 0, "chunks": []}
    result = kb.list_chunks(
        page_index=page_index,
        page_size=page_size,
        filename=filename,
        query=query,
    ) or {}
    items = list(result.get("items", []))
    if is_internal_filename is not None:
        items = [item for item in items if not is_internal_filename(item.get("filename"))]
    return {"ok": True, "count": len(items), "chunks": items}
