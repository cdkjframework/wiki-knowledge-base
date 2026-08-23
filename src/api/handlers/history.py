"""历史记录 HTTP 路由。"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote


def handle_get_history(http: Any, api: Any, path: str) -> bool:
    """处理 GET /history。"""
    if path != "/history":
        return False
    params = http._parse_query_params()
    page_index = http._page_index_from_params(params)
    limit = None
    action = None
    group_by_session = False

    if "limit" in params and params["limit"]:
        try:
            limit = int(params["limit"][-1])
        except Exception:
            http._bad_request("limit 必须是整数")
            return True
    if "action" in params and params["action"]:
        action = params["action"][-1]
    if "group_by_session" in params and params["group_by_session"]:
        group_by_session = params["group_by_session"][-1].lower() in ("true", "1", "yes")

    if group_by_session:
        result = {"ok": True, "sessions": api.get_history_sessions(limit=limit, action=action)}
    else:
        result = {"ok": True, "history": api.get_history(limit=limit, action=action)}

    http._ok(result, page_index=page_index)
    return True


def handle_delete_history(http: Any, api: Any, path: str) -> bool:
    """处理 DELETE /history、/history/{id}。"""
    if path == "/history":
        removed = api.clear_history()
        http._ok({"ok": True, "removed": removed})
        return True

    if path.startswith("/history/"):
        raw_id = unquote(path[len("/history/") :]).strip()
        if not raw_id:
            http._bad_request("缺少 history id 参数")
            return True
        try:
            item_id = int(raw_id)
        except Exception:
            http._bad_request("history id 必须是整数")
            return True
        removed = api.delete_history(item_id)
        if removed <= 0:
            http._not_found()
            return True
        http._ok({"ok": True, "removed": removed})
        return True

    return False
