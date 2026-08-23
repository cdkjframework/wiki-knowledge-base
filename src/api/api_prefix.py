"""
HTTP API 公共前缀。

业务接口一律挂在 /api 下，例如 /api/query、/api/kb/documents。
静态资源、文档页、前端 SPA 路由不加此前缀。
"""

from __future__ import annotations

import os

# 可用环境变量覆盖，默认 /api
_DEFAULT_PREFIX = "/api"


def api_prefix() -> str:
    raw = str(os.getenv("KB_API_PREFIX", _DEFAULT_PREFIX) or _DEFAULT_PREFIX).strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or "/api"


def strip_api_prefix(path: str) -> str | None:
    """
    若 path 带公共前缀，返回去掉前缀后的逻辑路径（以 / 开头）；
    否则返回 None（调用方按静态页 / SPA / 404 处理）。
    """
    prefix = api_prefix()
    p = str(path or "")
    if p == prefix:
        return "/"
    if p.startswith(prefix + "/"):
        rest = p[len(prefix) :]
        return rest if rest.startswith("/") else "/" + rest
    return None


def with_api_prefix(logical_path: str) -> str:
    """给逻辑路径加上公共前缀。"""
    prefix = api_prefix()
    path = str(logical_path or "/")
    if not path.startswith("/"):
        path = "/" + path
    if path == "/":
        return prefix + "/"
    return prefix + path
