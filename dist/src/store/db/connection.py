from typing import Any


class DatabaseConnection:
    def __init__(
        self,
        backend: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        connect_timeout: int = 5,
    ):
        name = (backend or "").strip().lower()
        if name in {"postgres", "postgresql"}:
            name = "postgresql"
        elif name == "mysql":
            name = "mysql"
        else:
            raise ValueError(f"Unsupported backend: {backend}")

        self.backend = name
        self.host = str(host or "127.0.0.1")
        self.port = int(port)
        self.user = str(user or "")
        self.password = str(password or "")
        self.database = str(database or "")
        self.connect_timeout = max(1, int(connect_timeout))
        self._driver = self._import_driver()

    def _import_driver(self):
        if self.backend == "mysql":
            try:
                import pymysql
            except ImportError as exc:
                raise RuntimeError(
                    "MySQL backend requires pymysql dependency."
                ) from exc
            return pymysql
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requires psycopg2-binary dependency."
            ) from exc
        return psycopg2

    def connect(self):
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

    def run_write(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        conn = self.connect()
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
