"""MCP capability configuration store."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .connection import DatabaseConnection


class McpConfigStore:
    """Database store for MCP capability configurations."""

    JSON_FIELDS = ["headers", "default_payload", "command_args", "env_vars"]

    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        if self.db.backend == "postgresql":
            sql = """
            CREATE TABLE IF NOT EXISTS mcp_configs (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                tool_name VARCHAR(255) NOT NULL,
                description TEXT,
                transport_type VARCHAR(32) NOT NULL DEFAULT 'http',
                base_url TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                http_method VARCHAR(16) NOT NULL DEFAULT 'POST',
                headers JSONB,
                default_payload JSONB,
                parameter_schema TEXT,
                keyword_hints TEXT,
                debug_hint TEXT,
                auth_type VARCHAR(32),
                auth_key_name VARCHAR(255),
                auth_secret TEXT,
                auth_secret_encrypted BOOLEAN DEFAULT FALSE,
                command TEXT,
                command_args JSONB,
                working_directory TEXT,
                env_vars JSONB,
                timeout FLOAT DEFAULT 30.0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        else:
            sql = """
            CREATE TABLE IF NOT EXISTS mcp_configs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                tool_name VARCHAR(255) NOT NULL,
                description TEXT,
                transport_type VARCHAR(32) NOT NULL DEFAULT 'http',
                base_url TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                http_method VARCHAR(16) NOT NULL DEFAULT 'POST',
                headers JSON,
                default_payload JSON,
                parameter_schema TEXT,
                keyword_hints TEXT,
                debug_hint TEXT,
                auth_type VARCHAR(32),
                auth_key_name VARCHAR(255),
                auth_secret TEXT,
                auth_secret_encrypted BOOLEAN DEFAULT FALSE,
                command TEXT,
                command_args JSON,
                working_directory TEXT,
                env_vars JSON,
                timeout FLOAT DEFAULT 30.0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_mcp_active (is_active),
                INDEX idx_mcp_transport (transport_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        self.db.run_write(sql)
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        desired_columns = {
            "transport_type": "VARCHAR(32) NOT NULL DEFAULT 'http'",
            "auth_type": "VARCHAR(32)",
            "auth_key_name": "VARCHAR(255)",
            "auth_secret": "TEXT",
            "auth_secret_encrypted": "BOOLEAN DEFAULT FALSE",
            "command": "TEXT",
            "command_args": "JSONB" if self.db.backend == "postgresql" else "JSON",
            "working_directory": "TEXT",
            "env_vars": "JSONB" if self.db.backend == "postgresql" else "JSON",
        }
        existing = self._existing_columns()
        for column, definition in desired_columns.items():
            if column in existing:
                continue
            sql = f"ALTER TABLE mcp_configs ADD COLUMN {column} {definition}"
            self.db.run_write(sql)

    def _existing_columns(self) -> set[str]:
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                if self.db.backend == "postgresql":
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                        ("mcp_configs",),
                    )
                else:
                    cur.execute("SHOW COLUMNS FROM mcp_configs")
                return {str(row[0]) for row in cur.fetchall()}
        finally:
            conn.close()

    def add_config(
        self,
        name: str,
        tool_name: str,
        base_url: str,
        endpoint: str,
        http_method: str = "POST",
        description: Optional[str] = None,
        transport_type: str = "http",
        headers: Optional[Dict[str, Any]] = None,
        default_payload: Optional[Dict[str, Any]] = None,
        parameter_schema: Optional[str] = None,
        keyword_hints: Optional[str] = None,
        debug_hint: Optional[str] = None,
        auth_type: Optional[str] = None,
        auth_key_name: Optional[str] = None,
        auth_secret: Optional[str] = None,
        auth_secret_encrypted: bool = False,
        command: Optional[str] = None,
        command_args: Optional[List[str]] = None,
        working_directory: Optional[str] = None,
        env_vars: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        is_active: bool = True,
    ) -> int:
        values = {
            "headers": json.dumps(headers or {}, ensure_ascii=False),
            "default_payload": json.dumps(default_payload or {}, ensure_ascii=False),
            "command_args": json.dumps(command_args or [], ensure_ascii=False),
            "env_vars": json.dumps(env_vars or {}, ensure_ascii=False),
        }
        if self.db.backend == "postgresql":
            sql = """
            INSERT INTO mcp_configs (
                name, tool_name, description, transport_type, base_url, endpoint, http_method,
                headers, default_payload, parameter_schema, keyword_hints, debug_hint,
                auth_type, auth_key_name, auth_secret, auth_secret_encrypted,
                command, command_args, working_directory, env_vars,
                timeout, is_active
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s::jsonb, %s, %s::jsonb,
                %s, %s
            )
            RETURNING id
            """
        else:
            sql = """
            INSERT INTO mcp_configs (
                name, tool_name, description, transport_type, base_url, endpoint, http_method,
                headers, default_payload, parameter_schema, keyword_hints, debug_hint,
                auth_type, auth_key_name, auth_secret, auth_secret_encrypted,
                command, command_args, working_directory, env_vars,
                timeout, is_active
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
            """
        params = (
            name,
            tool_name,
            description,
            transport_type,
            base_url,
            endpoint,
            http_method,
            values["headers"],
            values["default_payload"],
            parameter_schema,
            keyword_hints,
            debug_hint,
            auth_type,
            auth_key_name,
            auth_secret,
            auth_secret_encrypted,
            command,
            values["command_args"],
            working_directory,
            values["env_vars"],
            timeout,
            is_active,
        )
        if self.db.backend == "postgresql":
            conn = self.db.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    config_id = cur.fetchone()[0]
                conn.commit()
                return int(config_id)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        self.db.run_write(sql, params)
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT LAST_INSERT_ID()")
                return int(cur.fetchone()[0])
        finally:
            conn.close()

    def update_config(self, config_id: int, **kwargs: Any) -> bool:
        allowed_fields = {
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
            "auth_secret_encrypted",
            "command",
            "command_args",
            "working_directory",
            "env_vars",
            "timeout",
            "is_active",
        }
        updates: List[str] = []
        params: List[Any] = []
        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue
            if key in self.JSON_FIELDS and value is not None:
                value = json.dumps(value, ensure_ascii=False)
                updates.append(f"{key} = %s::jsonb" if self.db.backend == "postgresql" else f"{key} = %s")
            else:
                updates.append(f"{key} = %s")
            params.append(value)
        if not updates:
            return False
        updates.append("updated_at = %s")
        params.append(datetime.now(timezone.utc))
        params.append(config_id)
        sql = f"UPDATE mcp_configs SET {', '.join(updates)} WHERE id = %s"
        return self.db.run_write(sql, tuple(params)) > 0

    def delete_config(self, config_id: int) -> bool:
        return self.db.run_write("DELETE FROM mcp_configs WHERE id = %s", (config_id,)) > 0

    def get_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        return self._get_one("SELECT * FROM mcp_configs WHERE id = %s", (config_id,))

    def get_config_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return self._get_one("SELECT * FROM mcp_configs WHERE name = %s", (name,))

    def list_configs(self, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM mcp_configs"
        params: List[Any] = []
        if is_active is not None:
            sql += " WHERE is_active = %s"
            params.append(is_active)
        sql += " ORDER BY is_active DESC, name ASC"
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                columns = [desc[0] for desc in cur.description]
                return [self._row_to_dict(columns, row) for row in cur.fetchall()]
        finally:
            conn.close()

    def _get_one(self, sql: str, params: tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                if not row:
                    return None
                columns = [desc[0] for desc in cur.description]
                return self._row_to_dict(columns, row)
        finally:
            conn.close()

    @classmethod
    def _row_to_dict(cls, columns: List[str], row: tuple[Any, ...]) -> Dict[str, Any]:
        result = dict(zip(columns, row))
        for field in cls.JSON_FIELDS:
            value = result.get(field)
            if isinstance(value, str) and value:
                try:
                    result[field] = json.loads(value)
                except Exception:
                    result[field] = [] if field == "command_args" else {}
            elif value is None:
                result[field] = [] if field == "command_args" else {}
        for field in ["created_at", "updated_at"]:
            value = result.get(field)
            if isinstance(value, datetime):
                result[field] = value.isoformat()
        result["auth_secret_encrypted"] = bool(result.get("auth_secret_encrypted"))
        result["is_active"] = bool(result.get("is_active"))
        return result