"""
问答 HTTP 能力：路由实现见 handlers.query。
"""

from __future__ import annotations

from .bool_params import parse_deep_think
from .handlers.query import handle_get_query, handle_post_query

__all__ = ["handle_get_query", "handle_post_query", "parse_deep_think"]
