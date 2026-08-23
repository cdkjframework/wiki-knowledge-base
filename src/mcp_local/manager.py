import json
import logging
from typing import Any, Dict

try:
    from ..secret_cipher import decrypt_text, encrypt_text
    from ..store.db.connection import DatabaseConnection
    from ..store.db.mcp_config_store import McpConfigStore
    from .protocol_client import McpProtocolDispatcher
except ImportError:  # pragma: no cover
    from secret_cipher import decrypt_text, encrypt_text
    from store.db.connection import DatabaseConnection
    from store.db.mcp_config_store import McpConfigStore
    from mcp_local.protocol_client import McpProtocolDispatcher

logger = logging.getLogger(__name__)

MCP_DOC_PREFIX = "__mcp__/config_"
SENSITIVE_HEADER_KEYS = {"authorization", "x-api-key", "api-key", "apikey", "token"}


class McpConfigManager:
    """Manage MCP capability configs, secret handling and dispatch."""

    def __init__(self, db_connection: DatabaseConnection, secret_key: str | None = None):
        self.store = McpConfigStore(db_connection)
        self.secret_key = str(secret_key or "").strip() or None

    def add_mcp_config(
        self,
        name: str,
        tool_name: str,
        base_url: str,
        endpoint: str,
        http_method: str = "POST",
        description: str | None = None,
        transport_type: str = "http",
        headers: Dict[str, Any] | None = None,
        default_payload: Dict[str, Any] | None = None,
        parameter_schema: str | None = None,
        keyword_hints: str | None = None,
        debug_hint: str | None = None,
        auth_type: str | None = None,
        auth_key_name: str | None = None,
        auth_secret: str | None = None,
        command: str | None = None,
        command_args: list[str] | None = None,
        working_directory: str | None = None,
        env_vars: Dict[str, Any] | None = None,
        timeout: float = 30.0,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        try:
            secret_value, secret_encrypted = self._prepare_secret(auth_secret)
            config_id = self.store.add_config(
                name=name,
                tool_name=tool_name,
                description=description,
                transport_type=transport_type,
                base_url=base_url,
                endpoint=endpoint,
                http_method=http_method,
                headers=headers,
                default_payload=default_payload,
                parameter_schema=parameter_schema,
                keyword_hints=keyword_hints,
                debug_hint=debug_hint,
                auth_type=auth_type,
                auth_key_name=auth_key_name,
                auth_secret=secret_value,
                auth_secret_encrypted=secret_encrypted,
                command=command,
                command_args=command_args,
                working_directory=working_directory,
                env_vars=env_vars,
                timeout=timeout,
                is_active=is_active,
            )
            config = self.store.get_config(config_id)
            return {"ok": True, "config": self._sanitize_config(config)}
        except Exception as exc:
            logger.error("Failed to add MCP config: %s", exc)
            return {"ok": False, "error": str(exc)}

    def update_mcp_config(self, config_id: int, **kwargs: Any) -> Dict[str, Any]:
        try:
            updates = dict(kwargs)
            if "auth_secret" in updates:
                secret_value, secret_encrypted = self._prepare_secret(updates.get("auth_secret"))
                updates["auth_secret"] = secret_value
                updates["auth_secret_encrypted"] = secret_encrypted
            ok = self.store.update_config(config_id, **updates)
            if not ok:
                return {"ok": False, "error": "Config not found or no changes made"}
            return {"ok": True, "config": self._sanitize_config(self.store.get_config(config_id))}
        except Exception as exc:
            logger.error("Failed to update MCP config: %s", exc)
            return {"ok": False, "error": str(exc)}

    def delete_mcp_config(self, config_id: int) -> Dict[str, Any]:
        try:
            ok = self.store.delete_config(config_id)
            if not ok:
                return {"ok": False, "error": "Config not found"}
            return {"ok": True, "deleted": config_id}
        except Exception as exc:
            logger.error("Failed to delete MCP config: %s", exc)
            return {"ok": False, "error": str(exc)}

    def get_mcp_config(self, config_id: int | None = None, name: str | None = None) -> Dict[str, Any]:
        try:
            config = self.get_runtime_config(config_id=config_id, name=name, with_secret=False)
            if not config:
                return {"ok": False, "error": "Config not found"}
            return {"ok": True, "config": self._sanitize_config(config)}
        except Exception as exc:
            logger.error("Failed to get MCP config: %s", exc)
            return {"ok": False, "error": str(exc)}

    def get_runtime_config(
        self,
        config_id: int | None = None,
        name: str | None = None,
        with_secret: bool = True,
    ) -> Dict[str, Any] | None:
        if config_id is not None:
            config = self.store.get_config(config_id)
        elif name is not None:
            config = self.store.get_config_by_name(name)
        else:
            raise ValueError("Must provide config_id or name")
        if not config:
            return None
        runtime = dict(config)
        if with_secret:
            runtime["auth_secret"] = self._decode_secret(runtime)
            runtime["auth_secret_encrypted"] = False
        return runtime

    def list_mcp_configs(self, is_active: bool | None = None) -> Dict[str, Any]:
        try:
            configs = [self._sanitize_config(item) for item in self.store.list_configs(is_active=is_active)]
            return {"ok": True, "configs": configs, "count": len(configs)}
        except Exception as exc:
            logger.error("Failed to list MCP configs: %s", exc)
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def kb_doc_filename(config_id: int) -> str:
        return f"{MCP_DOC_PREFIX}{int(config_id)}.md"

    def build_kb_document(self, config: Dict[str, Any]) -> tuple[str, str]:
        filename = self.kb_doc_filename(int(config.get("id") or 0))
        headers = json.dumps(self._sanitize_headers(config.get("headers") or {}), ensure_ascii=False, indent=2)
        payload = json.dumps(config.get("default_payload") or {}, ensure_ascii=False, indent=2)
        command_args = json.dumps(config.get("command_args") or [], ensure_ascii=False, indent=2)
        env_vars = json.dumps(self._sanitize_headers(config.get("env_vars") or {}), ensure_ascii=False, indent=2)
        text = (
            "MCP能力配置文档\n\n"
            f"配置ID: {config.get('id')}\n"
            f"名称: {config.get('name') or ''}\n"
            f"工具名: {config.get('tool_name') or ''}\n"
            f"描述: {config.get('description') or ''}\n"
            f"关键词: {config.get('keyword_hints') or ''}\n"
            f"调试提示: {config.get('debug_hint') or ''}\n"
            f"传输类型: {config.get('transport_type') or 'http'}\n"
            f"基础地址: {config.get('base_url') or ''}\n"
            f"端点: {config.get('endpoint') or ''}\n"
            f"请求方法: {config.get('http_method') or 'POST'}\n"
            f"鉴权类型: {config.get('auth_type') or 'none'}\n"
            f"鉴权字段名: {config.get('auth_key_name') or ''}\n"
            f"命令: {config.get('command') or ''}\n"
            f"命令参数(JSON):\n{command_args}\n\n"
            f"工作目录: {config.get('working_directory') or ''}\n"
            f"环境变量(JSON):\n{env_vars}\n\n"
            f"参数说明: {config.get('parameter_schema') or ''}\n"
            f"请求头(JSON):\n{headers}\n\n"
            f"默认参数(JSON):\n{payload}\n"
        )
        return filename, text

    def dispatch_config(self, config: Dict[str, Any], analysis: Dict[str, Any] | None = None) -> Dict[str, Any]:
        analysis = analysis or {}
        runtime = dict(config)
        runtime["auth_secret"] = self._decode_secret(runtime)
        method = str(analysis.get("http_method") or runtime.get("http_method") or "POST").upper()
        base_url = str(runtime.get("base_url") or "").rstrip("/")
        endpoint = str(analysis.get("endpoint") or runtime.get("endpoint") or "").strip()
        path_params = analysis.get("path_params") if isinstance(analysis.get("path_params"), dict) else {}
        query_params = dict(analysis.get("query_params") or {}) if isinstance(analysis.get("query_params"), dict) else {}
        extra_headers = dict(analysis.get("headers") or {}) if isinstance(analysis.get("headers"), dict) else {}
        body = analysis.get("body") if isinstance(analysis.get("body"), dict) else None
        if body is None:
            body = dict(runtime.get("default_payload") or {})
        headers = dict(runtime.get("headers") or {})
        headers.update(extra_headers)
        try:
            if path_params:
                endpoint = endpoint.format(**{key: str(value) for key, value in path_params.items()})
        except Exception as exc:
            raise RuntimeError(f"路径参数替换失败: {exc}") from exc
        timeout = float(analysis.get("timeout") or runtime.get("timeout") or 30.0)
        headers, query_params = self._apply_auth(runtime, headers, query_params)
        dispatcher = McpProtocolDispatcher(timeout=timeout)
        transport_type = str(runtime.get("transport_type") or "http").strip().lower() or "http"
        if transport_type == "streamable_http":
            url = f"{base_url}/{endpoint.lstrip('/')}" if endpoint else base_url
            return dispatcher.dispatch_streamable_http(url=url, tool_name=str(runtime.get("tool_name") or ""), headers=headers, body=body)
        if transport_type == "stdio":
            return dispatcher.dispatch_stdio(
                command=str(runtime.get("command") or "").strip(),
                command_args=[str(item) for item in list(runtime.get("command_args") or [])],
                working_directory=str(runtime.get("working_directory") or "").strip() or None,
                env_vars=dict(runtime.get("env_vars") or {}),
                tool_name=str(runtime.get("tool_name") or ""),
                body=body,
            )
        url = f"{base_url}/{endpoint.lstrip('/')}" if endpoint else base_url
        return dispatcher.dispatch_http(method=method, url=url, headers=headers, query_params=query_params, body=body)

    def _prepare_secret(self, auth_secret: Any) -> tuple[str | None, bool]:
        secret_text = str(auth_secret or "").strip()
        if not secret_text:
            return None, False
        if not self.secret_key:
            raise ValueError("未配置 KB_SECRET_ENCRYPTION_KEY，无法加密保存鉴权密钥")
        return encrypt_text(secret_text, self.secret_key), True

    def _decode_secret(self, config: Dict[str, Any]) -> str | None:
        secret_value = str(config.get("auth_secret") or "").strip()
        if not secret_value:
            return None
        if not bool(config.get("auth_secret_encrypted")):
            return secret_value
        if not self.secret_key:
            raise ValueError("当前未配置 KB_SECRET_ENCRYPTION_KEY，无法解密 MCP 鉴权密钥")
        return decrypt_text(secret_value, self.secret_key)

    @staticmethod
    def _mask_secret(secret: str | None) -> str:
        raw = str(secret or "")
        if not raw:
            return ""
        if len(raw) <= 8:
            return "****"
        return raw[:3] + "****" + raw[-3:]

    @classmethod
    def _sanitize_headers(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        sanitized: Dict[str, Any] = {}
        for key, value in dict(payload or {}).items():
            if str(key).strip().lower() in SENSITIVE_HEADER_KEYS:
                sanitized[str(key)] = cls._mask_secret(str(value or ""))
            else:
                sanitized[str(key)] = value
        return sanitized

    def _sanitize_config(self, config: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not config:
            return None
        sanitized = dict(config)
        sanitized["headers"] = self._sanitize_headers(sanitized.get("headers") or {})
        sanitized["env_vars"] = self._sanitize_headers(sanitized.get("env_vars") or {})
        secret_value = str(sanitized.get("auth_secret") or "")
        sanitized["auth_secret"] = self._mask_secret(secret_value)
        sanitized["auth_secret_configured"] = bool(secret_value)
        return sanitized

    def _apply_auth(
        self,
        config: Dict[str, Any],
        headers: Dict[str, Any],
        query_params: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        auth_type = str(config.get("auth_type") or "").strip().lower()
        auth_key_name = str(config.get("auth_key_name") or "").strip()
        auth_secret = str(config.get("auth_secret") or "").strip()
        if not auth_type or not auth_secret:
            return headers, query_params
        if auth_type == "bearer":
            headers[auth_key_name or "Authorization"] = f"Bearer {auth_secret}"
        elif auth_type == "header":
            headers[auth_key_name or "X-API-Key"] = auth_secret
        elif auth_type == "query":
            query_params[auth_key_name or "api_key"] = auth_secret
        return headers, query_params