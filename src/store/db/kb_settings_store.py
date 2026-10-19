"""
知识库应用级设置落库（键值 JSON）。

当前主要用于 KB-20 检索/分片参数（含匹配度阈值 min_source_similarity），
避免只改 conf/config.json 导致多实例/重启后用户设置丢失。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from .connection import DatabaseConnection

logger = logging.getLogger(__name__)

RETRIEVAL_SETTING_KEY = "retrieval"


class KbSettingsStore:
    """kb_app_settings：setting_key → JSON value。"""

    def __init__(self, db_connection: DatabaseConnection, table_name: str = "kb_app_settings"):
        self.db = db_connection
        self.table = table_name
        self._ensure_table()

    def _ensure_table(self) -> None:
        if self.db.backend == "postgresql":
            sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                setting_key VARCHAR(64) PRIMARY KEY,
                setting_value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        else:
            sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                setting_key VARCHAR(64) NOT NULL PRIMARY KEY,
                setting_value JSON NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        self.db.run_write(sql)
        logger.info("KB app settings table ready: %s", self.table)

    def get_setting(self, key: str) -> Optional[Dict[str, Any]]:
        key = str(key or "").strip()
        if not key:
            return None
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT setting_value FROM {self.table} WHERE setting_key = %s",
                    (key,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        raw = row[0]
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                obj = json.loads(raw)
            except Exception:
                return None
            return obj if isinstance(obj, dict) else None
        return None

    def set_setting(self, key: str, value: Dict[str, Any]) -> None:
        key = str(key or "").strip()
        if not key:
            raise ValueError("setting_key 不能为空")
        if not isinstance(value, dict):
            raise ValueError("setting_value 必须是对象")

        payload = json.dumps(value, ensure_ascii=False)
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                if self.db.backend == "postgresql":
                    cur.execute(
                        f"""
                        INSERT INTO {self.table} (setting_key, setting_value, updated_at)
                        VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP)
                        ON CONFLICT (setting_key) DO UPDATE
                        SET setting_value = EXCLUDED.setting_value,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (key, payload),
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {self.table} (setting_key, setting_value)
                        VALUES (%s, CAST(%s AS JSON))
                        ON DUPLICATE KEY UPDATE
                            setting_value = VALUES(setting_value)
                        """,
                        (key, payload),
                    )
            conn.commit()
        finally:
            conn.close()

    def get_retrieval_settings(self) -> Optional[Dict[str, Any]]:
        return self.get_setting(RETRIEVAL_SETTING_KEY)

    def set_retrieval_settings(self, settings: Dict[str, Any]) -> None:
        self.set_setting(RETRIEVAL_SETTING_KEY, settings)
