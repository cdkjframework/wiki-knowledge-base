"""模型配置 HTTP 路由。"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import unquote


def _require_model_manager(http: Any, api: Any) -> bool:
    if api._model_config_manager:
        return True
    http._bad_request("模型配置管理不可用（需要启用数据库后端）")
    return False


def handle_get_model(http: Any, api: Any, path: str) -> bool:
    """处理 GET /model/*。"""
    if path == "/model/configs":
        if not _require_model_manager(http, api):
            return True
        params = http._parse_query_params()
        provider = http._get_param_value(params, "provider", "").strip() or None
        is_active_str = http._get_param_value(params, "is_active", "").strip()
        is_active = None
        if is_active_str:
            is_active = is_active_str.lower() in ("true", "1", "yes")
        model_type = http._get_param_value(params, "model_type", "").strip() or None
        result = api._model_config_manager.list_model_configs(
            provider=provider,
            is_active=is_active,
            model_type=model_type,
        )
        http._ok(result)
        return True

    # 必须先于 /model/config/{id}，避免 "default" 被当成 name
    if path == "/model/config/default":
        if not _require_model_manager(http, api):
            return True
        http._ok(api._model_config_manager.get_default_config())
        return True

    if path == "/model/providers":
        if not _require_model_manager(http, api):
            return True
        http._ok(api._model_config_manager.get_supported_providers())
        return True

    if path.startswith("/model/config/"):
        if not _require_model_manager(http, api):
            return True
        identifier = unquote(path[len("/model/config/") :]).strip()
        if not identifier:
            http._bad_request("缺少 config_id 或 name 参数")
            return True
        try:
            config_id = int(identifier)
            result = api._model_config_manager.get_model_config(config_id=config_id)
        except ValueError:
            result = api._model_config_manager.get_model_config(name=identifier)
        http._ok(result)
        return True

    return False


def handle_post_model(http: Any, api: Any, path: str, body: Dict[str, Any]) -> bool:
    """处理 POST /model/*。"""
    page_index = http._page_index_from_body(body)

    if path == "/model/config":
        if not _require_model_manager(http, api):
            return True
        required_fields = ["name", "provider", "base_url", "model_name"]
        for field in required_fields:
            if not body.get(field):
                http._bad_request(f"缺少必填字段: {field}")
                return True
        result = api._model_config_manager.add_model_config(
            name=body["name"],
            provider=body["provider"],
            base_url=body["base_url"],
            model_name=body["model_name"],
            api_key=body.get("api_key"),
            model_type=body.get("model_type", "chat"),
            temperature=body.get("temperature", 0.7),
            max_tokens=body.get("max_tokens"),
            timeout=body.get("timeout", 30.0),
            extra_headers=body.get("extra_headers"),
            extra_params=body.get("extra_params"),
            is_active=body.get("is_active", True),
            is_default=body.get("is_default", False),
            description=body.get("description"),
        )
        http._ok(result, page_index=page_index)
        return True

    if path == "/model/config/test":
        if not _require_model_manager(http, api):
            return True
        result = api._model_config_manager.test_config(
            config_id=body.get("config_id"),
            name=body.get("name"),
            config_data=body.get("config"),
        )
        http._ok(result, page_index=page_index)
        return True

    if path == "/model/config/bootstrap":
        if not _require_model_manager(http, api):
            return True
        result = api._model_config_manager.bootstrap_default_configs()
        http._ok(result, page_index=page_index)
        return True

    if path.startswith("/model/config/") and path.endswith("/default"):
        if not _require_model_manager(http, api):
            return True
        config_id_str = path[len("/model/config/") : -len("/default")]
        try:
            config_id = int(config_id_str)
        except ValueError:
            http._bad_request("config_id 必须是整数")
            return True
        result = api._model_config_manager.set_default_config(config_id)
        http._ok(result, page_index=page_index)
        return True

    return False


def handle_put_model(http: Any, api: Any, path: str) -> bool:
    """处理 PUT /model/config/{id}。"""
    if not path.startswith("/model/config/"):
        return False
    if not _require_model_manager(http, api):
        return True
    config_id_str = unquote(path[len("/model/config/") :]).strip()
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
        "provider",
        "base_url",
        "api_key",
        "model_name",
        "model_type",
        "temperature",
        "max_tokens",
        "timeout",
        "extra_headers",
        "extra_params",
        "is_active",
        "is_default",
        "description",
    ]
    for field in allowed_fields:
        if field in body:
            update_fields[field] = body[field]
    result = api._model_config_manager.update_model_config(config_id, **update_fields)
    http._ok(result, page_index=page_index)
    return True


def handle_delete_model(http: Any, api: Any, path: str) -> bool:
    """处理 DELETE /model/config/{id}。"""
    if not path.startswith("/model/config/"):
        return False
    if not _require_model_manager(http, api):
        return True
    config_id_str = unquote(path[len("/model/config/") :]).strip()
    try:
        config_id = int(config_id_str)
    except ValueError:
        http._bad_request("config_id 必须是整数")
        return True
    result = api._model_config_manager.delete_model_config(config_id)
    if not result.get("ok"):
        http._not_found()
        return True
    http._ok(result)
    return True
