"""
Model Provider Configuration Store
Manages AI model provider configurations in database
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .connection import DatabaseConnection

logger = logging.getLogger(__name__)


class ModelConfigStore:
    """Database store for AI model provider configurations"""
    
    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection
        self._ensure_table()
    
    def _ensure_table(self):
        """Create model_configs table if not exists"""
        if self.db.backend == "postgresql":
            sql = """
            CREATE TABLE IF NOT EXISTS model_configs (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                provider VARCHAR(100) NOT NULL,
                base_url TEXT NOT NULL,
                api_key TEXT,
                model_name VARCHAR(255) NOT NULL,
                model_type VARCHAR(50) DEFAULT 'chat',
                temperature FLOAT DEFAULT 0.7,
                max_tokens INTEGER,
                timeout FLOAT DEFAULT 30.0,
                extra_headers JSONB,
                extra_params JSONB,
                is_active BOOLEAN DEFAULT TRUE,
                is_default BOOLEAN DEFAULT FALSE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        else:  # MySQL
            sql = """
            CREATE TABLE IF NOT EXISTS model_configs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                provider VARCHAR(100) NOT NULL,
                base_url TEXT NOT NULL,
                api_key TEXT,
                model_name VARCHAR(255) NOT NULL,
                model_type VARCHAR(50) DEFAULT 'chat',
                temperature FLOAT DEFAULT 0.7,
                max_tokens INT,
                timeout FLOAT DEFAULT 30.0,
                extra_headers JSON,
                extra_params JSON,
                is_active BOOLEAN DEFAULT TRUE,
                is_default BOOLEAN DEFAULT FALSE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_provider (provider),
                INDEX idx_active (is_active),
                INDEX idx_default (is_default)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        try:
            self.db.run_write(sql)
            logger.info("Model configs table created or already exists")
        except Exception as exc:
            logger.error(f"Failed to create model_configs table: {exc}")
            raise
    
    def add_config(
        self,
        name: str,
        provider: str,
        base_url: str,
        model_name: str,
        api_key: Optional[str] = None,
        model_type: str = "chat",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 30.0,
        extra_headers: Optional[Dict[str, str]] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
        is_default: bool = False,
        description: Optional[str] = None,
    ) -> int:
        """Add new model configuration"""
        # If setting as default, unset other defaults
        if is_default:
            self._unset_all_defaults()
        
        extra_headers_json = json.dumps(extra_headers or {})
        extra_params_json = json.dumps(extra_params or {})
        
        if self.db.backend == "postgresql":
            sql = """
            INSERT INTO model_configs (
                name, provider, base_url, api_key, model_name, model_type,
                temperature, max_tokens, timeout, extra_headers, extra_params,
                is_active, is_default, description
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
            RETURNING id
            """
        else:  # MySQL
            sql = """
            INSERT INTO model_configs (
                name, provider, base_url, api_key, model_name, model_type,
                temperature, max_tokens, timeout, extra_headers, extra_params,
                is_active, is_default, description
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        
        params = (
            name, provider, base_url, api_key, model_name, model_type,
            temperature, max_tokens, timeout, extra_headers_json, extra_params_json,
            is_active, is_default, description
        )
        
        if self.db.backend == "postgresql":
            conn = self.db.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    config_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Added model config: {name} (id={config_id})")
                return config_id
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            self.db.run_write(sql, params)
            # Get last insert ID
            conn = self.db.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT LAST_INSERT_ID()")
                    config_id = cur.fetchone()[0]
                logger.info(f"Added model config: {name} (id={config_id})")
                return config_id
            finally:
                conn.close()
    
    def update_config(
        self,
        config_id: int,
        **kwargs: Any,
    ) -> bool:
        """Update model configuration"""
        allowed_fields = {
            "name", "provider", "base_url", "api_key", "model_name", "model_type",
            "temperature", "max_tokens", "timeout", "extra_headers", "extra_params",
            "is_active", "is_default", "description"
        }
        
        updates = []
        params = []
        
        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue
            
            if key == "is_default" and value:
                self._unset_all_defaults()
            
            if key in {"extra_headers", "extra_params"} and value is not None:
                value = json.dumps(value)
                if self.db.backend == "postgresql":
                    updates.append(f"{key} = %s::jsonb")
                else:
                    updates.append(f"{key} = %s")
            else:
                updates.append(f"{key} = %s")
            params.append(value)
        
        if not updates:
            return False
        
        # Add updated_at
        updates.append("updated_at = %s")
        params.append(datetime.now(timezone.utc))
        params.append(config_id)
        
        sql = f"UPDATE model_configs SET {', '.join(updates)} WHERE id = %s"
        count = self.db.run_write(sql, tuple(params))
        
        if count > 0:
            logger.info(f"Updated model config id={config_id}")
        return count > 0
    
    def delete_config(self, config_id: int) -> bool:
        """Delete model configuration"""
        sql = "DELETE FROM model_configs WHERE id = %s"
        count = self.db.run_write(sql, (config_id,))
        if count > 0:
            logger.info(f"Deleted model config id={config_id}")
        return count > 0
    
    def get_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        """Get model configuration by ID"""
        sql = "SELECT * FROM model_configs WHERE id = %s"
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (config_id,))
                row = cur.fetchone()
                if not row:
                    return None
                columns = [desc[0] for desc in cur.description]
                return self._row_to_dict(columns, row)
        finally:
            conn.close()
    
    def get_config_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get model configuration by name"""
        sql = "SELECT * FROM model_configs WHERE name = %s"
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (name,))
                row = cur.fetchone()
                if not row:
                    return None
                columns = [desc[0] for desc in cur.description]
                return self._row_to_dict(columns, row)
        finally:
            conn.close()
    
    def get_default_config(self) -> Optional[Dict[str, Any]]:
        """Get default model configuration"""
        sql = "SELECT * FROM model_configs WHERE is_default = TRUE AND is_active = TRUE LIMIT 1"
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
                if not row:
                    return None
                columns = [desc[0] for desc in cur.description]
                return self._row_to_dict(columns, row)
        finally:
            conn.close()
    
    def list_configs(
        self,
        provider: Optional[str] = None,
        is_active: Optional[bool] = None,
        model_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List model configurations with optional filters"""
        conditions = []
        params = []
        
        if provider is not None:
            conditions.append("provider = %s")
            params.append(provider)
        
        if is_active is not None:
            conditions.append("is_active = %s")
            params.append(is_active)
        
        if model_type is not None:
            conditions.append("model_type = %s")
            params.append(model_type)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM model_configs {where_clause} ORDER BY is_default DESC, name ASC"
        
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                columns = [desc[0] for desc in cur.description]
                return [self._row_to_dict(columns, row) for row in cur.fetchall()]
        finally:
            conn.close()
    
    def set_default(self, config_id: int) -> bool:
        """Set a configuration as default"""
        self._unset_all_defaults()
        sql = "UPDATE model_configs SET is_default = TRUE, updated_at = %s WHERE id = %s"
        count = self.db.run_write(sql, (datetime.now(timezone.utc), config_id))
        if count > 0:
            logger.info(f"Set model config id={config_id} as default")
        return count > 0
    
    def _unset_all_defaults(self):
        """Unset all default flags"""
        sql = "UPDATE model_configs SET is_default = FALSE WHERE is_default = TRUE"
        self.db.run_write(sql)
    
    def _row_to_dict(self, columns: List[str], row: tuple) -> Dict[str, Any]:
        """Convert database row to dictionary"""
        result = dict(zip(columns, row))
        
        # Parse JSON fields
        for field in ["extra_headers", "extra_params"]:
            if field in result and result[field]:
                try:
                    if isinstance(result[field], str):
                        result[field] = json.loads(result[field])
                except Exception:
                    result[field] = {}
        
        # Convert timestamps to ISO format
        for field in ["created_at", "updated_at"]:
            if field in result and result[field]:
                if isinstance(result[field], datetime):
                    result[field] = result[field].isoformat()
        
        return result
