"""
知识库核心域（检索 / 索引 / 分片）。

由 knowledge_base.py 渐进迁入；当前已落地文档列表门面。
"""

from .documents import list_chunks, list_documents

__all__ = ["list_chunks", "list_documents"]
