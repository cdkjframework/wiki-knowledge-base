import time

from .connection import DatabaseConnection
from ..interfaces import SessionIdStore
from .utils import _VALID_TABLE_RE


class DatabaseSessionIdStore(SessionIdStore):
    def __init__(
        self,
        backend: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        table: str = "kb_sessions",
        connect_timeout: int = 5,
    ):
        table_name = (table or "").strip()
        if not _VALID_TABLE_RE.match(table_name):
            raise ValueError(f"Invalid session table name: {table!r}")

        self.table = table_name
        self._conn = DatabaseConnection(
            backend=backend,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=connect_timeout,
        )
        self._ensure_table()

    def _ensure_table(self) -> None:
        if self._conn.backend == "mysql":
            ddl = f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                user_id VARCHAR(256) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_user_id (user_id),
                KEY idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            self._conn.run_write(ddl)
            return

        create_table = f"""
        CREATE TABLE IF NOT EXISTS {self.table} (
            id BIGSERIAL PRIMARY KEY,
            user_id VARCHAR(256) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_idx_user = (
            f"CREATE INDEX IF NOT EXISTS idx_{self.table}_user_id ON {self.table}(user_id);"
        )
        create_idx_created = (
            f"CREATE INDEX IF NOT EXISTS idx_{self.table}_created_at ON {self.table}(created_at);"
        )
        self._conn.run_write(create_table)
        self._conn.run_write(create_idx_user)
        self._conn.run_write(create_idx_created)

    def new_session_id(self, user_id: str) -> str:
        user = str(user_id or "").strip()
        if not user:
            raise ValueError("user_id is required")

        conn = self._conn.connect()
        try:
            with conn.cursor() as cur:
                if self._conn.backend == "postgresql":
                    cur.execute(
                        f"INSERT INTO {self.table} (user_id) VALUES (%s) RETURNING id",
                        (user,),
                    )
                    row = cur.fetchone()
                    seq = int(row[0]) if row else None
                else:
                    cur.execute(
                        f"INSERT INTO {self.table} (user_id) VALUES (%s)",
                        (user,),
                    )
                    seq = int(cur.lastrowid) if getattr(cur, "lastrowid", None) else None
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        if seq is None:
            raise RuntimeError("Failed to allocate session id")

        return f"s_{user}_{seq}_{int(time.time())}"
