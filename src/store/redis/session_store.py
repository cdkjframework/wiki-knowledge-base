import time

from .connection import RedisConnection
from ..interfaces import SessionIdStore


class RedisSessionIdStore(SessionIdStore):
    def __init__(
        self,
        host: str,
        port: int,
        database: int,
        password: str | None = None,
        key_prefix: str = "kb:session:",
    ):
        self._conn = RedisConnection(
            host=host,
            port=port,
            database=database,
            password=password,
        )
        self._key_prefix = str(key_prefix or "kb:session:")

    def new_session_id(self, user_id: str) -> str:
        user = str(user_id or "").strip()
        if not user:
            raise ValueError("user_id is required")
        key = f"{self._key_prefix}{user}"
        seq = self._conn.incr(key)
        return f"s_{user}_{seq}_{int(time.time())}"
