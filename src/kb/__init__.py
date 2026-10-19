"""
知识库核心域（检索 / 索引 / 分片）。

由 knowledge_base.py 渐进迁入；当前已落地文档列表门面、KB-20 检索配置与 KB-01 混合检索辅助模块。
"""

from .bm25_index import Bm25Index, build_bm25, tokenize
from .documents import list_chunks, list_documents
from .hybrid import rrf_fuse
from .retrieval_settings import (
    apply_settings_to_config,
    apply_settings_to_runtime,
    normalize_settings,
    snapshot_from_runtime,
)

__all__ = [
    "Bm25Index",
    "build_bm25",
    "tokenize",
    "rrf_fuse",
    "list_chunks",
    "list_documents",
    "apply_settings_to_config",
    "apply_settings_to_runtime",
    "normalize_settings",
    "snapshot_from_runtime",
]
