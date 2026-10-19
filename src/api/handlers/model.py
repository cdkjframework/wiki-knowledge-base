"""模型配置 HTTP 路由。"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import unquote

try:
    from ...model_config_manager import (
        is_local_hf_provider,
        normalize_base_url_for_provider,
        normalize_model_type,
    )
except ImportError:  # pragma: no cover
    from model_config_manager import (  # type: ignore
        is_local_hf_provider,
        normalize_base_url_for_provider,
        normalize_model_type,
    )


def _require_model_manager(http: Any, api: Any) -> bool:
    if api._model_config_manager:
        return True
    http._bad_request("模型配置管理不可用（需要启用数据库后端）")
    return False


def _apply_kb_runtime(
    api: Any,
    cfg: Dict[str, Any],
    *,
    api_key: Any = None,
    include_api_key: bool = False,
) -> Dict[str, Any] | None:
    """把默认配置热切到 KB 运行时；embedding/rerank/chat。"""
    if api.kb is None:
        return None
    mt = normalize_model_type(cfg.get("model_type"))
    provider = str(cfg.get("provider") or "")
    model_name = str(cfg.get("model_name") or "")
    base_url = str(cfg.get("base_url") or "") or None
    timeout = cfg.get("timeout")
    # 编辑页常传空 api_key 表示「不改密钥」——仍用库里已存的
    if include_api_key:
        raw = "" if api_key is None else str(api_key).strip()
        key = raw or cfg.get("api_key")
    else:
        key = cfg.get("api_key")
    if mt in {"embedding", "rerank"}:
        return api.kb.apply_retrieval_backend(
            kind=mt,
            provider=provider,
            model_name=model_name,
            base_url=base_url,
            api_key=key,
            dimension=cfg.get("dimension"),
            timeout=timeout,
        )
    if mt == "chat":
        return api.kb.apply_chat_backend(
            provider=provider,
            model_name=model_name,
            base_url=base_url,
            api_key=key,
            timeout=timeout,
            temperature=cfg.get("temperature"),
            max_tokens=cfg.get("max_tokens"),
        )
    return None


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

    if path == "/model/local-models":
        params = http._parse_query_params()
        kind = http._get_param_value(params, "model_type", "").strip() or http._get_param_value(
            params, "kind", ""
        ).strip()
        http._ok(api.kb.list_local_hf_models(kind=kind or None))
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
        required_fields = ["name", "provider", "model_name"]
        for field in required_fields:
            if not body.get(field):
                http._bad_request(f"缺少必填字段: {field}")
                return True
        provider = str(body.get("provider") or "").strip()
        base_url = normalize_base_url_for_provider(provider, body.get("base_url"))
        if not is_local_hf_provider(provider) and not base_url:
            http._bad_request("缺少必填字段: base_url")
            return True
        result = api._model_config_manager.add_model_config(
            name=body["name"],
            provider=provider,
            base_url=base_url,
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
            dimension=body.get("dimension"),
            max_input_length=body.get("max_input_length"),
        )
        # 新增并勾选默认时同步运行时
        if result.get("ok") and body.get("is_default") and api.kb is not None:
            cfg = result.get("config") or {}
            runtime = _apply_kb_runtime(
                api,
                {
                    **cfg,
                    "provider": cfg.get("provider") or provider,
                    "model_name": cfg.get("model_name") or body["model_name"],
                    "base_url": cfg.get("base_url") or base_url,
                    "model_type": cfg.get("model_type") or body.get("model_type"),
                    "dimension": cfg.get("dimension")
                    if cfg.get("dimension") is not None
                    else body.get("dimension"),
                    "timeout": cfg.get("timeout")
                    if cfg.get("timeout") is not None
                    else body.get("timeout"),
                    "temperature": cfg.get("temperature")
                    if cfg.get("temperature") is not None
                    else body.get("temperature"),
                    "max_tokens": cfg.get("max_tokens")
                    if cfg.get("max_tokens") is not None
                    else body.get("max_tokens"),
                    "api_key": body.get("api_key") if "api_key" in body else cfg.get("api_key"),
                },
                api_key=body.get("api_key"),
                include_api_key=True,
            )
            if runtime is not None:
                result["runtime"] = runtime
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

    if path == "/model/config/list-models":
        if not _require_model_manager(http, api):
            return True
        provider = str(body.get("provider") or "").strip()
        if not provider:
            http._bad_request("缺少必填字段: provider")
            return True
        result = api._model_config_manager.list_remote_models(
            provider=provider,
            base_url=str(body.get("base_url") or ""),
            api_key=body.get("api_key"),
            timeout=float(body.get("timeout") or 30.0),
            config_id=body.get("config_id"),
            extra_headers=body.get("extra_headers"),
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
        if result.get("ok") and api.kb is not None:
            cfg = result.get("config") or {}
            # 清掉旧 client 缓存，避免编辑后仍命中过期连接
            cache = getattr(api._model_config_manager, "_client_cache", None)
            if isinstance(cache, dict):
                cache.clear()
            runtime = _apply_kb_runtime(api, cfg)
            if runtime is not None:
                result["runtime"] = runtime
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
        "dimension",
        "max_input_length",
    ]
    for field in allowed_fields:
        if field in body:
            update_fields[field] = body[field]
    if "provider" in update_fields or "base_url" in update_fields:
        provider = str(update_fields.get("provider") or "").strip()
        if not provider:
            existing = api._model_config_manager.store.get_config(config_id) or {}
            provider = str(existing.get("provider") or "")
        if "base_url" in update_fields or provider:
            update_fields["base_url"] = normalize_base_url_for_provider(
                provider, update_fields.get("base_url")
            )
    result = api._model_config_manager.update_model_config(config_id, **update_fields)
    # 保存后若仍是该类型默认配置，立刻热切换运行时（不依赖请求体是否带 is_default）
    if result.get("ok") and api.kb is not None:
        cfg = result.get("config") or {}
        if cfg.get("is_default"):
            runtime = _apply_kb_runtime(
                api,
                cfg,
                api_key=body.get("api_key") if "api_key" in body else None,
                include_api_key="api_key" in body,
            )
            if runtime is not None:
                result["runtime"] = runtime
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
