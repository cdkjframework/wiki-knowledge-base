"""会话 HTTP 路由。"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import unquote


def handle_get_session(http: Any, api: Any, path: str) -> bool:
    """处理 GET /session。"""
    if path != "/session":
        return False
    params = http._parse_query_params()
    page_index = http._page_index_from_params(params)
    user_id = None
    if "user_id" in params and params["user_id"]:
        user_id = params["user_id"][-1].strip() or None
    if "userId" in params and params["userId"]:
        user_id = params["userId"][-1].strip() or user_id
    if not user_id:
        http._bad_request("缺少 user_id 参数")
        return True
    session_id = api._new_session_id(user_id)
    http._ok(
        {"ok": True, "user_id": user_id, "session_id": session_id},
        page_index=page_index,
    )
    return True


def handle_post_session(http: Any, api: Any, path: str, body: Dict[str, Any]) -> bool:
    """处理 POST /session。"""
    if path != "/session":
        return False
    page_index = http._page_index_from_body(body)
    user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None
    if not user_id:
        http._bad_request("缺少 user_id 参数")
        return True
    session_id = api._new_session_id(user_id)
    http._ok(
        {"ok": True, "user_id": user_id, "session_id": session_id},
        page_index=page_index,
    )
    return True


def handle_delete_session(http: Any, api: Any, path: str) -> bool:
    """处理 DELETE /session/{id}。"""
    if not path.startswith("/session/"):
        return False
    session_id = unquote(path[len("/session/") :]).strip()
    if not session_id:
        http._bad_request("缺少 session_id 参数")
        return True
    try:
        removed = api.delete_session(session_id)
        if removed <= 0:
            http._not_found()
            return True
        http._ok({"ok": True, "removed": removed})
    except NotImplementedError:
        http._bad_request("当前后端不支持删除整段会话")
    return True
