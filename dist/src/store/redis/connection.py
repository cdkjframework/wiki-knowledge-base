class RedisConnection:
    def __init__(
        self,
        host: str,
        port: int,
        database: int,
        password: str | None = None,
    ):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "Redis backend requires redis dependency."
            ) from exc

        self._client = redis.Redis(
            host=str(host or "127.0.0.1"),
            port=int(port),
            db=int(database),
            password=(password or None),
            decode_responses=True,
        )
        self._client.ping()

    def incr(self, key: str) -> int:
        return int(self._client.incr(key))
