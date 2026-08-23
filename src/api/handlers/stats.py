"""GET /stats。"""

from __future__ import annotations

from typing import Any


def handle_get_stats(http: Any, api: Any, path: str) -> bool:
    """
    处理 GET /stats。

    Returns:
        是否已处理该路径
    """
    if path != "/stats":
        return False
    http._ok(api.get_knowledge_base_stats())
    return True
