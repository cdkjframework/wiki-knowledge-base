"""
API 包说明：业务路由已迁至 handlers/；http_server 负责服务器壳与静态资源。
"""

from .http_server import (
    API,
    CHAT_MCP_SOURCE_FILENAME,
    HttpApiServer,
    KnowledgeBaseApi,
)

__all__ = [
    "API",
    "CHAT_MCP_SOURCE_FILENAME",
    "HttpApiServer",
    "KnowledgeBaseApi",
]
