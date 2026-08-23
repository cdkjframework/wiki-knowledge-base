import re
from typing import Any, Optional


def _get_logger():
    import logging

    return logging.getLogger(__name__)


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
        client_encoding: Optional[str] = None,
        options: Optional[str] = None,
        auto_create_database: bool = True,
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
        self.client_encoding = (str(client_encoding).strip() if client_encoding else "")
        self.options = (str(options).strip() if options else "")
        self.auto_create_database = bool(auto_create_database)
        self._driver = self._import_driver()
        self._db_create_attempted = False
        self._db_auto_created = False

    def _build_postgresql_options(self) -> str:
        """Build robust PostgreSQL options for Windows locale compatibility."""
        base = self.options.strip()
        lower = base.lower()
        extras: list[str] = []

        # Always prefer UTF-8 client decoding if caller did not explicitly set it.
        if "client_encoding" not in lower:
            enc = self.client_encoding or "UTF8"
            extras.append(f"-c client_encoding={enc}")

        # Force English messages so libpq error decoding is ASCII-safe on Windows.
        if "lc_messages" not in lower:
            extras.append("-c lc_messages=C")

        return (base + " " + " ".join(extras)).strip() if extras else base

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
            kwargs = {
                "host": self.host,
                "port": self.port,
                "user": self.user,
                "password": self.password,
                "database": self.database,
                "connect_timeout": self.connect_timeout,
                "charset": "utf8mb4",
            }
            try:
                return self._driver.connect(**kwargs)
            except Exception as exc:
                if self._is_missing_mysql_database_error(exc) and self._try_create_database_once():
                    self._create_database_for_mysql()
                    return self._driver.connect(**kwargs)
                raise
        options = self._build_postgresql_options()
        self._ensure_postgresql_database_exists_once(options=options)
        kwargs = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "dbname": self.database,
            "connect_timeout": self.connect_timeout,
        }
        if options:
            kwargs["options"] = options
        try:
            return self._driver.connect(
                **kwargs,
            )
        except UnicodeDecodeError as exc:
            # psycopg2 on some Windows locales may fail to decode localized
            # libpq/winsock errors and raise UnicodeDecodeError directly.
            # Retry once with the safest locale options in case current options
            # were ignored or partially applied by caller overrides.
            retry_kwargs = dict(kwargs)
            retry_kwargs["options"] = "-c client_encoding=UTF8 -c lc_messages=C"
            try:
                return self._driver.connect(**retry_kwargs)
            except Exception:
                pass

            # If auto-create is enabled, still attempt create+retry once.
            if self._try_create_database_once():
                try:
                    self._create_database_for_postgresql(options=retry_kwargs.get("options", options))
                    return self._driver.connect(**retry_kwargs)
                except Exception:
                    pass
            raise RuntimeError(
                "PostgreSQL connection failed with a locale decoding error on "
                "Windows. Please verify host/port/network reachability, "
                "database credentials, and PostgreSQL server/client encoding. "
                f"target={self.host}:{self.port}/{self.database} user={self.user}"
            ) from exc
        except Exception as exc:
            if self._is_missing_postgresql_database_error(exc) and self._try_create_database_once():
                self._create_database_for_postgresql(options=options)
                try:
                    return self._driver.connect(**kwargs)
                except UnicodeDecodeError as inner_exc:
                    raise RuntimeError(
                        "PostgreSQL connection failed with a locale decoding error on "
                        "Windows. Please verify host/port/network reachability and "
                        "database credentials."
                    ) from inner_exc
            raise

    def _ensure_postgresql_database_exists_once(self, options: str = "") -> None:
        """Best-effort proactive DB creation for PostgreSQL when enabled.

        This avoids relying solely on locale-sensitive error parsing when
        the target database is missing.
        """
        if self.backend != "postgresql":
            return
        if not self.auto_create_database:
            return
        if self._db_create_attempted:
            return
        self._db_create_attempted = True
        if not self._is_safe_database_name(self.database):
            raise RuntimeError(f"Unsafe database name for auto-create: {self.database!r}")

        logger = _get_logger()
        admin_kwargs = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "dbname": "postgres",
            "connect_timeout": self.connect_timeout,
        }
        if options:
            admin_kwargs["options"] = options

        try:
            admin_conn = self._driver.connect(**admin_kwargs)
        except Exception as exc:
            logger.warning("Auto-create precheck skipped: cannot connect admin DB: %s", exc)
            return

        try:
            admin_conn.autocommit = True
            with admin_conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.database,))
                exists = cur.fetchone() is not None
                if exists:
                    return
                sql = f"CREATE DATABASE {self._quote_postgresql_identifier(self.database)} ENCODING 'UTF8'"
                cur.execute(sql)
                self._db_auto_created = True
                logger.info("Auto-created PostgreSQL database: %s", self.database)
        finally:
            admin_conn.close()

    def _try_create_database_once(self) -> bool:
        if not self.auto_create_database:
            return False
        if self._db_create_attempted:
            return False
        self._db_create_attempted = True
        return True

    @staticmethod
    def _quote_mysql_identifier(identifier: str) -> str:
        return "`" + identifier.replace("`", "``") + "`"

    @staticmethod
    def _quote_postgresql_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _is_safe_database_name(name: str) -> bool:
        if not name:
            return False
        return bool(re.match(r"^[A-Za-z0-9_\-]+$", name))

    def _create_database_for_mysql(self) -> None:
        if not self._is_safe_database_name(self.database):
            raise RuntimeError(f"Unsafe database name for auto-create: {self.database!r}")
        admin_conn = self._driver.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            connect_timeout=self.connect_timeout,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            sql = (
                "CREATE DATABASE IF NOT EXISTS "
                f"{self._quote_mysql_identifier(self.database)} "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            with admin_conn.cursor() as cur:
                cur.execute(sql)
            self._db_auto_created = True
        finally:
            admin_conn.close()

    def _create_database_for_postgresql(self, options: str = "") -> None:
        if not self._is_safe_database_name(self.database):
            raise RuntimeError(f"Unsafe database name for auto-create: {self.database!r}")
        admin_kwargs = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "dbname": "postgres",
            "connect_timeout": self.connect_timeout,
        }
        if options:
            admin_kwargs["options"] = options
        admin_conn = self._driver.connect(**admin_kwargs)
        try:
            admin_conn.autocommit = True
            sql = f"CREATE DATABASE {self._quote_postgresql_identifier(self.database)} ENCODING 'UTF8'"
            with admin_conn.cursor() as cur:
                try:
                    cur.execute(sql)
                    self._db_auto_created = True
                except Exception as exc:
                    # 42P04: duplicate_database
                    if getattr(exc, "pgcode", "") != "42P04":
                        raise
                    self._db_auto_created = True
        finally:
            admin_conn.close()

    def did_auto_create_database(self) -> bool:
        return bool(self._db_auto_created)

    @staticmethod
    def _is_missing_mysql_database_error(exc: Exception) -> bool:
        args = getattr(exc, "args", ())
        if not args:
            return False
        code = args[0]
        return str(code) == "1049"

    @staticmethod
    def _is_missing_postgresql_database_error(exc: Exception) -> bool:
        # 3D000: invalid_catalog_name (database does not exist)
        if getattr(exc, "pgcode", "") == "3D000":
            return True
        msg = str(exc).lower()
        return "does not exist" in msg and "database" in msg

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
