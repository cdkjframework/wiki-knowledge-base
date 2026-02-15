import json
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_VALID_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class InMemoryHistoryStore:
    def __init__(self):
        self._items: List[Dict[str, Any]] = []
        self._next_id = 1

    def append(
        self,
        timestamp: str,
        action: str,
        request: Dict[str, Any],
        response: Dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "id": int(self._next_id),
            "timestamp": timestamp,
            "action": action,
            "request": request,
        }
        self._next_id += 1
        if response is not None:
            item["response"] = response
        if error:
            item["error"] = error
        self._items.append(item)
        return item

    def get(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        records = self._items
        if action:
            records = [x for x in records if x.get("action") == action]
        if limit is not None:
            records = records[-max(0, int(limit)) :]
        return list(records)

    def clear(self) -> int:
        count = len(self._items)
        self._items.clear()
        return count

    def delete(self, item_id: int) -> int:
        target = int(item_id)
        before = len(self._items)
        self._items = [x for x in self._items if int(x.get("id", -1)) != target]
        return 1 if len(self._items) != before else 0


class DatabaseHistoryStore:
    def __init__(
        self,
        backend: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        table: str = "kb_history",
        connect_timeout: int = 5,
    ):
        name = (backend or "").strip().lower()
        if name in {"postgres", "postgresql"}:
            name = "postgresql"
        elif name == "mysql":
            name = "mysql"
        else:
            raise ValueError(f"Unsupported history backend: {backend}")

        table_name = (table or "").strip()
        if not _VALID_TABLE_RE.match(table_name):
            raise ValueError(f"Invalid history table name: {table!r}")

        self.backend = name
        self.host = str(host or "127.0.0.1")
        self.port = int(port)
        self.user = str(user or "")
        self.password = str(password or "")
        self.database = str(database or "")
        self.table = table_name
        self.connect_timeout = max(1, int(connect_timeout))
        self._driver = self._import_driver()
        self._ensure_table()

    def _import_driver(self):
        if self.backend == "mysql":
            try:
                import pymysql
            except ImportError as exc:
                raise RuntimeError(
                    "History backend is mysql but dependency pymysql is not installed."
                ) from exc
            return pymysql
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError(
                "History backend is postgresql but dependency psycopg2-binary is not installed."
            ) from exc
        return psycopg2

    def _connect(self):
        if self.backend == "mysql":
            return self._driver.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=self.connect_timeout,
                charset="utf8mb4",
            )
        return self._driver.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=self.database,
            connect_timeout=self.connect_timeout,
        )

    def _run_write(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                count = int(cur.rowcount or 0)
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_table(self) -> None:
        if self.backend == "mysql":
            ddl = f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                timestamp VARCHAR(64) NOT NULL,
                action VARCHAR(64) NOT NULL,
                request_json LONGTEXT NOT NULL,
                response_json LONGTEXT NULL,
                error LONGTEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_action (action),
                KEY idx_timestamp (timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            self._run_write(ddl)
            return

        create_table = f"""
        CREATE TABLE IF NOT EXISTS {self.table} (
            id BIGSERIAL PRIMARY KEY,
            timestamp VARCHAR(64) NOT NULL,
            action VARCHAR(64) NOT NULL,
            request_json TEXT NOT NULL,
            response_json TEXT NULL,
            error TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_idx_action = (
            f"CREATE INDEX IF NOT EXISTS idx_{self.table}_action ON {self.table}(action);"
        )
        create_idx_timestamp = (
            f"CREATE INDEX IF NOT EXISTS idx_{self.table}_timestamp ON {self.table}(timestamp);"
        )
        self._run_write(create_table)
        self._run_write(create_idx_action)
        self._run_write(create_idx_timestamp)

    @staticmethod
    def _safe_json_loads(raw: str | None) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
            return {"value": obj}
        except Exception:
            return {"raw": str(raw)}

    def append(
        self,
        timestamp: str,
        action: str,
        request: Dict[str, Any],
        response: Dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Dict[str, Any]:
        request_json = json.dumps(request, ensure_ascii=False)
        response_json = None if response is None else json.dumps(response, ensure_ascii=False)

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if self.backend == "postgresql":
                    cur.execute(
                        f"""
                        INSERT INTO {self.table}
                        (timestamp, action, request_json, response_json, error)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (timestamp, action, request_json, response_json, error),
                    )
                    row = cur.fetchone()
                    item_id = int(row[0]) if row else None
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {self.table}
                        (timestamp, action, request_json, response_json, error)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (timestamp, action, request_json, response_json, error),
                    )
                    item_id = int(cur.lastrowid) if getattr(cur, "lastrowid", None) else None
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        item: Dict[str, Any] = {
            "timestamp": timestamp,
            "action": action,
            "request": request,
        }
        if item_id is not None:
            item["id"] = item_id
        if response is not None:
            item["response"] = response
        if error:
            item["error"] = error
        return item

    def get(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where = ""
        if action:
            where = " WHERE action = %s"
            params.append(action)

        if limit is None:
            order_clause = " ORDER BY id ASC"
        else:
            lim = max(0, int(limit))
            if lim == 0:
                return []
            order_clause = " ORDER BY id DESC LIMIT %s"
            params.append(lim)

        sql = (
            f"SELECT id, timestamp, action, request_json, response_json, error "
            f"FROM {self.table}{where}{order_clause}"
        )

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        finally:
            conn.close()

        out: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {
                "id": int(row[0]),
                "timestamp": str(row[1]),
                "action": str(row[2]),
                "request": self._safe_json_loads(row[3]),
            }
            response = self._safe_json_loads(row[4])
            if row[4] is not None:
                item["response"] = response
            if row[5]:
                item["error"] = str(row[5])
            out.append(item)

        if limit is not None:
            out.reverse()
        return out

    def clear(self) -> int:
        return self._run_write(f"DELETE FROM {self.table}")

    def delete(self, item_id: int) -> int:
        return self._run_write(f"DELETE FROM {self.table} WHERE id = %s", (int(item_id),))
