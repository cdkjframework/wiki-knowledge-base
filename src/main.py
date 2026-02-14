import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict

try:
    from .api import HttpApiServer, KnowledgeBaseApi
    from .knowledge_base import KnowledgeBase
except ImportError:  # pragma: no cover
    from api import HttpApiServer, KnowledgeBaseApi
    from knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class Main:
    """Application startup entry: initialize KB and preload models."""

    def __init__(self, **knowledge_base_kwargs: Any):
        self._knowledge_base_kwargs = dict(knowledge_base_kwargs)
        self._kb: KnowledgeBase | None = None
        self._api: KnowledgeBaseApi | None = None
        self._last_warmup: Dict[str, Any] | None = None

    @staticmethod
    def _ensure_warmup_success(
        warmup: Dict[str, Any],
        preload_embedding: bool,
        preload_reranker: bool,
    ) -> None:
        errors = []
        if preload_embedding and not bool(warmup.get("embedding_loaded")):
            errors.append(f"embedding not loaded: {warmup.get('embedding_error', 'unknown error')}")
        if preload_reranker and not bool(warmup.get("reranker_loaded")):
            errors.append(f"reranker not loaded: {warmup.get('reranker_error', 'unknown error')}")
        if errors:
            raise RuntimeError("Model warmup failed at startup: " + "; ".join(errors))

    def startup(
        self, preload_embedding: bool = True, preload_reranker: bool = True
    ) -> KnowledgeBaseApi:
        if self._api is not None:
            return self._api

        logger.info("Initializing knowledge base")
        self._kb = KnowledgeBase(**self._knowledge_base_kwargs)
        warmup = self._kb.warmup_models(
            load_embedding=preload_embedding,
            load_reranker=preload_reranker,
        )
        self._last_warmup = dict(warmup)
        logger.info("Warmup status: %s", warmup)
        self._ensure_warmup_success(
            warmup,
            preload_embedding=preload_embedding,
            preload_reranker=preload_reranker,
        )
        self._api = KnowledgeBaseApi(self._kb)
        self._api.log_event(
            "startup",
            {
                "preload_embedding": preload_embedding,
                "preload_reranker": preload_reranker,
                "warmup": warmup,
                "knowledge_base_stats": self._kb.stats(),
            },
        )
        return self._api

    def load_models(
        self, preload_embedding: bool = True, preload_reranker: bool = True
    ) -> Dict[str, Any]:
        if self._kb is None:
            self._kb = KnowledgeBase(**self._knowledge_base_kwargs)
            if self._api is None:
                self._api = KnowledgeBaseApi(self._kb)
        warmup = self._kb.warmup_models(
            load_embedding=preload_embedding,
            load_reranker=preload_reranker,
        )
        self._last_warmup = dict(warmup)
        logger.info("Load models status: %s", warmup)
        self._ensure_warmup_success(
            warmup,
            preload_embedding=preload_embedding,
            preload_reranker=preload_reranker,
        )
        if self._api is not None:
            self._api.log_event(
                "load_models",
                {
                    "preload_embedding": preload_embedding,
                    "preload_reranker": preload_reranker,
                    "warmup": warmup,
                },
            )
        return warmup

    def get_api(self) -> KnowledgeBaseApi:
        return self.startup()

    def start_http(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        preload_embedding: bool = True,
        preload_reranker: bool = True,
    ) -> HttpApiServer:
        api = self.startup(
            preload_embedding=preload_embedding,
            preload_reranker=preload_reranker,
        )
        logger.info("Starting HTTP server on %s:%s", host, port)
        return HttpApiServer(api=api, host=host, port=port)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Knowledge base startup entry.")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP bind host.")
    parser.add_argument("--port", type=int, default=5000, help="HTTP bind port.")
    parser.add_argument(
        "--no-preload-embedding",
        action="store_true",
        help="Skip embedding model warmup at startup.",
    )
    parser.add_argument(
        "--no-preload-reranker",
        action="store_true",
        help="Skip reranker model warmup at startup.",
    )
    return parser.parse_args()


def _setup_logging() -> Path:
    project_root = Path(__file__).resolve().parent.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"knowledge-base-{datetime.now().strftime('%Y%m%d')}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    return log_file


def _main() -> None:
    log_file = _setup_logging()
    logger.info("Log file: %s", log_file)
    args = _parse_args()
    logger.info(
        "Startup args: host=%s port=%s preload_embedding=%s preload_reranker=%s",
        args.host,
        args.port,
        not args.no_preload_embedding,
        not args.no_preload_reranker,
    )
    app = Main()
    server = app.start_http(
        host=args.host,
        port=args.port,
        preload_embedding=not args.no_preload_embedding,
        preload_reranker=not args.no_preload_reranker,
    )
    payload = {
        "ok": True,
        "message": "knowledge-base http started",
        "address": server.address,
        "warmup": app._last_warmup or {},
        "stats": app.get_api().get_knowledge_base_stats().get("stats", {}),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by keyboard interrupt")
        print(json.dumps({"ok": True, "message": "shutdown requested"}, ensure_ascii=False))
    finally:
        logger.info("Shutting down HTTP server")
        server.shutdown()


if __name__ == "__main__":
    _main()
