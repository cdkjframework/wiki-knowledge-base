"""
前端静态资源解析（P6：默认服务 Vue 构建产物）。

优先 frontend/dist；遗留静态台仅在启用开关时从 archive/web（或 web/）提供。
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from .api_prefix import api_prefix, strip_api_prefix
except ImportError:  # pragma: no cover
    from api_prefix import api_prefix, strip_api_prefix

# 与 HTTP API 精确对齐的「逻辑路径」（不含 /api 前缀）
_API_EXACT: frozenset[str] = frozenset(
    {
        "/query",
        "/stats",
        "/health",
        "/session",
        "/history",
        "/kb",
        "/kb/documents",
        "/kb/chunks",
        "/kb/file",
        "/kb/files",
        "/kb/document",
        "/kb/chunks/rebuild",
        "/model/configs",
        "/model/providers",
        "/model/config",
        "/model/config/default",
        "/model/config/test",
        "/model/config/bootstrap",
        "/mcp/configs",
        "/mcp/config",
        "/mcp/debug",
    }
)

# 文档类路径（不加 /api 前缀，仍禁止 SPA fallback）
# /api-docs 已迁入 Vue 路由，由前端托管，不再挡 SPA
_DOCS_EXACT: frozenset[str] = frozenset(
    {
        "/docs",
        "/docs/",
    }
)

_KB_API_SEGMENTS: frozenset[str] = frozenset(
    {
        "documents",
        "chunks",
        "file",
        "files",
        "document",
        "chunk",
    }
)


def resolve_frontend_dist(project_root: Path) -> Path:
    """Vue 构建输出目录。"""
    return project_root / "frontend" / "dist"


def resolve_legacy_web_dir(project_root: Path) -> Path:
    """
    遗留静态台目录：优先 archive/web，其次兼容旧路径 web/。
    """
    archived = project_root / "archive" / "web"
    if archived.is_dir():
        return archived
    return project_root / "web"


def legacy_web_enabled() -> bool:
    """是否临时启用遗留 /legacy-ui（默认关闭）。"""
    raw = str(os.getenv("KB_SERVE_LEGACY_WEB", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _commercial_api_paths() -> frozenset[str]:
    """商业专属 API 路径；社区包无 business 时为空。"""
    try:
        from ...commercial.business.license.http import LICENSE_LOGICAL_PATH
    except ImportError:
        try:
            from commercial.business.license.http import LICENSE_LOGICAL_PATH
        except ImportError:
            return frozenset()
    return frozenset({LICENSE_LOGICAL_PATH})


def _is_logical_api_path(logical: str) -> bool:
    if logical in _API_EXACT or logical in _commercial_api_paths():
        return True
    if logical.startswith("/history/") or logical.startswith("/session/"):
        return True
    if logical.startswith("/model/config/") or logical.startswith("/mcp/config/"):
        return True
    if logical.startswith("/kb/"):
        seg = logical[len("/kb/") :].split("/", 1)[0]
        return seg in _KB_API_SEGMENTS
    return False


def is_api_or_docs_path(path: str) -> bool:
    """判断是否为后端 API / 文档路径（不应 SPA fallback）。"""
    if path in _DOCS_EXACT or path.startswith("/docs/"):
        return True
    # 裸 /health 留给探活；业务接口必须带 /api
    if path == "/health":
        return True
    logical = strip_api_prefix(path)
    if logical is None:
        return False
    return _is_logical_api_path(logical)


def should_spa_fallback(path: str) -> bool:
    """
    无扩展名的前端路由走 index.html。

    带扩展名的请求视为静态资源（缺失则 404，不做 SPA）。
    """
    if is_api_or_docs_path(path):
        return False
    # /api 本身不是页面
    if path == api_prefix() or path == api_prefix() + "/":
        return False
    name = path.rstrip("/").rsplit("/", 1)[-1]
    if not name or name in {".", ".."}:
        return True
    return "." not in name
