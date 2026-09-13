"""
知识库核心域（检索 / 索引 / 分片）。

由 knowledge_base.py 渐进迁入；当前已落地文档列表门面与 KB-20 检索配置。
"""

from .documents import list_chunks, list_documents
from .retrieval_settings import (
    apply_settings_to_config,
    apply_settings_to_runtime,
    normalize_settings,
    snapshot_from_runtime,
)

__all__ = [
    "list_chunks",
    "list_documents",
    "apply_settings_to_config",
    "apply_settings_to_runtime",
    "normalize_settings",
    "snapshot_from_runtime",
]
