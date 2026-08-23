"""MCP 配置 HTTP 路由。"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import unquote


def _require_mcp_manager(http: Any, api: Any) -> bool:
    if api._mcp_manager:
        return True
    http._bad_request("MCP 配置管理不可用（需要启用数据库后端）")
    return False


def handle_get_mcp(http: Any, api: Any, path: str) -> bool:
    """处理 GET /mcp/*。"""
    if path == "/mcp/configs":
        if not _require_mcp_manager(http, api):
            return True
        params = http._parse_query_params()
        is_active_str = http._get_param_value(params, "is_active", "").strip()
        is_active = None
        if is_active_str:
            is_active = is_active_str.lower() in ("true", "1", "yes")
        http._ok(api._mcp_manager.list_mcp_configs(is_active=is_active))
        return True

    if path.startswith("/mcp/config/"):
        if not _require_mcp_manager(http, api):
            return True
        identifier = unquote(path[len("/mcp/config/") :]).strip()
        if not identifier:
            http._bad_request("缺少 config_id 或 name 参数")
            return True
        try:
            result = api._mcp_manager.get_mcp_config(config_id=int(identifier))
        except ValueError:
            result = api._mcp_manager.get_mcp_config(name=identifier)
        http._ok(result)
        return True

    return False


def handle_post_mcp(http: Any, api: Any, path: str, body: Dict[str, Any]) -> bool:
    """处理 POST /mcp/config、/mcp/debug。"""
    page_index = http._page_index_from_body(body)

    if path == "/mcp/config":
        if not _require_mcp_manager(http, api):
            return True
        transport_type = str(body.get("transport_type") or "http").strip().lower() or "http"
        required_fields = ["name", "tool_name"]
        for field in required_fields:
            if not body.get(field):
                http._bad_request(f"缺少必填字段: {field}")
                return True
        if transport_type in {"http", "streamable_http"} and not str(body.get("base_url") or "").strip():
            http._bad_request("transport_type 为 http 或 streamable_http 时必须填写 base_url")
            return True
        if transport_type == "stdio" and not str(body.get("command") or "").strip():
            http._bad_request("transport_type 为 stdio 时必须填写 command")
            return True
        result = api._mcp_manager.add_mcp_config(
            name=body["name"],
            tool_name=body["tool_name"],
            transport_type=transport_type,
            base_url=str(body.get("base_url") or ""),
            endpoint=str(body.get("endpoint") or ""),
            http_method=body.get("http_method", "POST"),
            description=body.get("description"),
            headers=body.get("headers"),
            default_payload=body.get("default_payload"),
            parameter_schema=body.get("parameter_schema"),
            keyword_hints=body.get("keyword_hints"),
            debug_hint=body.get("debug_hint"),
            auth_type=body.get("auth_type"),
            auth_key_name=body.get("auth_key_name"),
            auth_secret=body.get("auth_secret"),
            command=body.get("command"),
            command_args=body.get("command_args") if isinstance(body.get("command_args"), list) else None,
            working_directory=body.get("working_directory"),
            env_vars=body.get("env_vars") if isinstance(body.get("env_vars"), dict) else None,
            timeout=body.get("timeout", 30.0),
            is_active=body.get("is_active", True),
        )
        if result.get("ok"):
            api._sync_single_mcp_document(result.get("config"))
        http._ok(result, page_index=page_index)
        return True

    if path == "/mcp/debug":
        if not _require_mcp_manager(http, api):
            return True
        config_id = body.get("config_id")
        if config_id is None:
            http._bad_request("缺少 config_id 参数")
            return True
        user_request = str(body.get("user_request") or body.get("query") or "").strip()
        if not user_request:
            http._bad_request("缺少 user_request 参数")
            return True
        model_config_id = body.get("model_config_id")
        if model_config_id is not None:
            model_config_id = int(model_config_id)
        result = api.debug_mcp(
            config_id=int(config_id),
            user_request=user_request,
            input_params=body.get("input_params") if isinstance(body.get("input_params"), dict) else None,
            model_config_id=model_config_id,
            model_config_name=str(body.get("model_config_name") or "").strip() or None,
            use_default_model_config=bool(body.get("use_default_model_config", True)),
        )
        http._ok(result, page_index=page_index)
        return True

    return False


def handle_put_mcp(http: Any, api: Any, path: str) -> bool:
    """处理 PUT /mcp/config/{id}。"""
    if not path.startswith("/mcp/config/"):
        return False
    if not _require_mcp_manager(http, api):
        return True
    config_id_str = unquote(path[len("/mcp/config/") :]).strip()
    try:
        config_id = int(config_id_str)
    except ValueError:
        http._bad_request("config_id 必须是整数")
        return True
    body = http._read_json()
    page_index = http._page_index_from_body(body)
    update_fields = {}
    allowed_fields = [
        "name",
        "tool_name",
        "description",
        "transport_type",
        "base_url",
        "endpoint",
        "http_method",
        "headers",
        "default_payload",
        "parameter_schema",
        "keyword_hints",
        "debug_hint",
        "auth_type",
        "auth_key_name",
        "auth_secret",
        "command",
        "command_args",
        "working_directory",
        "env_vars",
        "timeout",
        "is_active",
    ]
    for field in allowed_fields:
        if field in body:
            update_fields[field] = body[field]
    result = api._mcp_manager.update_mcp_config(config_id, **update_fields)
    if result.get("ok"):
        api._sync_single_mcp_document(result.get("config"))
    http._ok(result, page_index=page_index)
    return True


def handle_delete_mcp(http: Any, api: Any, path: str) -> bool:
    """处理 DELETE /mcp/config/{id}。"""
    if not path.startswith("/mcp/config/"):
        return False
    if not _require_mcp_manager(http, api):
        return True
    config_id_str = unquote(path[len("/mcp/config/") :]).strip()
    try:
        config_id = int(config_id_str)
    except ValueError:
        http._bad_request("config_id 必须是整数")
        return True
    result = api._mcp_manager.delete_mcp_config(config_id)
    if not result.get("ok"):
        http._not_found()
        return True
    api._remove_single_mcp_document(config_id)
    http._ok(result)
    return True
