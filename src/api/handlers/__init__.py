"""
HTTP 路由 handler 包：从 http_server.Handler 渐进拆出。

约定：各 handle_* 处理完请求后返回 True；未匹配返回 False。
http 参数为鸭子类型，需具备 _ok / _bad_request / _send_sse 等响应方法。
"""

from .history import handle_delete_history, handle_get_history
from .kb import (
    handle_delete_kb,
    handle_get_kb,
    handle_post_kb,
    handle_put_kb,
)
from .mcp import (
    handle_delete_mcp,
    handle_get_mcp,
    handle_post_mcp,
    handle_put_mcp,
)
from .metrics import handle_get_metrics
from .model import (
    handle_delete_model,
    handle_get_model,
    handle_post_model,
    handle_put_model,
)
from .query import handle_get_query, handle_post_query
from .session import (
    handle_delete_session,
    handle_get_session,
    handle_post_session,
)
from .stats import handle_get_stats

__all__ = [
    "handle_delete_history",
    "handle_delete_kb",
    "handle_delete_mcp",
    "handle_delete_model",
    "handle_delete_session",
    "handle_get_history",
    "handle_get_kb",
    "handle_get_mcp",
    "handle_get_metrics",
    "handle_get_model",
    "handle_get_query",
    "handle_get_session",
    "handle_get_stats",
    "handle_post_kb",
    "handle_post_mcp",
    "handle_post_model",
    "handle_post_query",
    "handle_post_session",
    "handle_put_kb",
    "handle_put_mcp",
    "handle_put_model",
]
