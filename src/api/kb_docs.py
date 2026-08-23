"""
知识库文档 HTTP 能力：路由实现见 handlers.kb；领域门面见 src.kb.documents。
"""

from __future__ import annotations

from ..kb.documents import list_chunks, list_documents
from .handlers.kb import (
    handle_delete_kb,
    handle_get_kb,
    handle_post_kb,
    handle_put_kb,
)

__all__ = [
    "handle_delete_kb",
    "handle_get_kb",
    "handle_post_kb",
    "handle_put_kb",
    "list_chunks",
    "list_documents",
]
