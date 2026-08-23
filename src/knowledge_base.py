import gc
import json
import logging
import math
import os
import re
import shutil
import time
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

# Work around Windows OpenMP runtime conflicts (libomp vs libiomp5) that can
# happen when mixing binary wheels (e.g. torch/faiss/tokenizers).
if os.name == "nt":
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None
try:
    import zvec  # type: ignore
except Exception:  # pragma: no cover
    zvec = None
import numpy as np
import torch

try:
    from .lm_studio_client import LmStudioClient
except ImportError:  # pragma: no cover
    from lm_studio_client import LmStudioClient
try:
    from .chat_model import ChatModel
except ImportError:  # pragma: no cover
    from chat_model import ChatModel
try:
    from .document_parsers import BaseDocumentParser, KnowledgeBaseDocumentParser
except ImportError:  # pragma: no cover
    from document_parsers import BaseDocumentParser, KnowledgeBaseDocumentParser
logger = logging.getLogger(__name__)

# transformers/huggingface_hub old call paths still pass resume_download.
warnings.filterwarnings(
    "ignore",
    message=r"`resume_download` is deprecated",
    category=FutureWarning,
    module=r"huggingface_hub\.file_download",
)


@dataclass
class _Chunk:
    filename: str
    text: str


class _NumpyIndexFlatIP:
    """Small FAISS-like fallback index using numpy inner product search."""

    def __init__(self, dimension: int):
        self.dimension = int(dimension)
        self._vectors = np.zeros((0, self.dimension), dtype=np.float32)

    @property
    def ntotal(self) -> int:
        return int(self._vectors.shape[0])

    def add(self, vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim != 2:
            raise ValueError("vectors must be 2D")
        if arr.shape[1] != self.dimension:
            raise ValueError(
                f"vector dimension mismatch: expected {self.dimension}, got {arr.shape[1]}"
            )
        if arr.shape[0] == 0:
            return
        self._vectors = np.vstack([self._vectors, arr]).astype(np.float32, copy=False)

    def search(self, queries: np.ndarray, top_n: int) -> Tuple[np.ndarray, np.ndarray]:
        q = np.asarray(queries, dtype=np.float32)
        if q.ndim != 2 or q.shape[1] != self.dimension:
            raise ValueError(
                f"query dimension mismatch: expected (*, {self.dimension}), got {q.shape}"
            )
        n_queries = q.shape[0]
        k = max(1, int(top_n))
        if self.ntotal == 0:
            scores = np.full((n_queries, k), -np.inf, dtype=np.float32)
            indices = np.full((n_queries, k), -1, dtype=np.int64)
            return scores, indices

        sims = q @ self._vectors.T
        use_k = min(k, self.ntotal)
        part = np.argpartition(-sims, use_k - 1, axis=1)[:, :use_k]
        part_scores = np.take_along_axis(sims, part, axis=1)
        order = np.argsort(-part_scores, axis=1)
        top_indices = np.take_along_axis(part, order, axis=1)
        top_scores = np.take_along_axis(part_scores, order, axis=1).astype(
            np.float32, copy=False
        )

        if use_k < k:
            pad_scores = np.full((n_queries, k - use_k), -np.inf, dtype=np.float32)
            pad_indices = np.full((n_queries, k - use_k), -1, dtype=np.int64)
            top_scores = np.hstack([top_scores, pad_scores])
            top_indices = np.hstack([top_indices.astype(np.int64, copy=False), pad_indices])
        else:
            top_indices = top_indices.astype(np.int64, copy=False)
        return top_scores, top_indices


class _ZvecCollectionIndex:
    """
    把官方 zvec（Collection API）包成 FAISS 风格：add / search / ntotal。

    配置里写的 vector_backend=zvec 指的是 PyPI 上的 zvec，不是假想的 IndexFlatIP。
    """

    VECTOR_FIELD = "embedding"
    COLLECTION_NAME = "kb_vectors"
    _INSERT_BATCH = 512

    def __init__(self, path: Path, dimension: int, collection: Any):
        self.path = Path(path)
        self.dimension = int(dimension)
        self._col = collection

    @classmethod
    def create(cls, path: Path, dimension: int) -> "_ZvecCollectionIndex":
        if zvec is None:
            raise RuntimeError("zvec module is not available")
        path = Path(path)
        cls._remove_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        schema = zvec.CollectionSchema(
            name=cls.COLLECTION_NAME,
            vectors=[
                zvec.VectorSchema(
                    cls.VECTOR_FIELD,
                    zvec.DataType.VECTOR_FP32,
                    int(dimension),
                    index_param=zvec.FlatIndexParam(metric_type=zvec.MetricType.IP),
                )
            ],
        )
        collection = zvec.create_and_open(path=str(path), schema=schema)
        return cls(path, int(dimension), collection)

    @classmethod
    def open_existing(cls, path: Path, dimension: int | None = None) -> "_ZvecCollectionIndex":
        if zvec is None:
            raise RuntimeError("zvec module is not available")
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"zvec collection path not found: {path}")
        collection = zvec.open(str(path))
        dim = int(dimension) if dimension else cls._dimension_from_schema(collection)
        return cls(path, dim, collection)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    @staticmethod
    def _dimension_from_schema(collection: Any) -> int:
        vectors = getattr(getattr(collection, "schema", None), "vectors", None) or []
        if not vectors:
            raise RuntimeError("zvec collection schema has no vector fields")
        dim = getattr(vectors[0], "dimension", None)
        if not dim:
            raise RuntimeError("zvec collection schema missing vector dimension")
        return int(dim)

    @property
    def ntotal(self) -> int:
        stats = getattr(self._col, "stats", None)
        if stats is None:
            return 0
        return int(getattr(stats, "doc_count", 0) or 0)

    def add(self, vectors: np.ndarray) -> None:
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim != 2:
            raise ValueError("vectors must be 2D")
        if arr.shape[1] != self.dimension:
            raise ValueError(
                f"vector dimension mismatch: expected {self.dimension}, got {arr.shape[1]}"
            )
        if arr.shape[0] == 0:
            return
        start = self.ntotal
        for offset in range(0, arr.shape[0], self._INSERT_BATCH):
            batch = arr[offset : offset + self._INSERT_BATCH]
            docs = [
                zvec.Doc(
                    id=str(start + offset + i),
                    vectors={self.VECTOR_FIELD: row.tolist()},
                )
                for i, row in enumerate(batch)
            ]
            self._col.insert(docs)

    def search(self, queries: np.ndarray, top_n: int) -> Tuple[np.ndarray, np.ndarray]:
        q = np.asarray(queries, dtype=np.float32)
        if q.ndim != 2 or q.shape[1] != self.dimension:
            raise ValueError(
                f"query dimension mismatch: expected (*, {self.dimension}), got {q.shape}"
            )
        n_queries = q.shape[0]
        k = max(1, int(top_n))
        scores = np.full((n_queries, k), -np.inf, dtype=np.float32)
        indices = np.full((n_queries, k), -1, dtype=np.int64)
        if self.ntotal == 0:
            return scores, indices

        for qi in range(n_queries):
            hits = self._col.query(
                queries=zvec.Query(self.VECTOR_FIELD, vector=q[qi].tolist()),
                topk=k,
            )
            if not hits:
                continue
            for hi, doc in enumerate(hits[:k]):
                try:
                    indices[qi, hi] = int(getattr(doc, "id"))
                except (TypeError, ValueError):
                    indices[qi, hi] = -1
                score = getattr(doc, "score", None)
                scores[qi, hi] = float(score) if score is not None else -np.inf
        return scores, indices

    def flush(self) -> None:
        flush = getattr(self._col, "flush", None)
        if callable(flush):
            flush()

    def close(self) -> None:
        """释放进程内写锁，否则同路径无法再次 open/create。"""
        col = self._col
        self._col = None
        if col is None:
            return
        try:
            flush = getattr(col, "flush", None)
            if callable(flush):
                flush()
        except Exception:
            pass
        del col
        gc.collect()


class KnowledgeBase:
    """
    本地知识库系统，支持文档管理、向量搜索和聊天功能。
    
    功能特性：
    - 使用 Qwen3 Embedding 模型进行文本向量化
    - 使用 Qwen3 Reranker 模型进行结果重排序
    - 使用 FAISS 进行高效向量搜索
    - 支持 PDF、Word、TXT 等多种文件格式
    - 支持分块管理和智能检索
    - 可选的 LM Studio 本地大模型聊天集成
    
    搜索接口：
        search(query: str, k: int = None, relevance_threshold: float = None) 
        -> List[Tuple[filename, chunk_text, score]]
    
    示例用法：
        >>> kb = KnowledgeBase()
        >>> kb.add_document("sample.txt", "这是一份示例文档")
        >>> results = kb.search("示例")
        >>> for filename, text, score in results:
        ...     print(f"{filename}: {score:.4f}")
    """

    def __init__(
        self,
        dimension: int | None = None,
        persist_dir: str | None = None,
        embedding_model: str | None = None,
        reranker_model: str | None = None,
        device: str | None = None,
        local_files_only: bool | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        """
        初始化知识库系统。
        
        参数说明：
            dimension (int, 可选)
                向量维度。如果为 None，将从配置文件或嵌入模型自动推断。
                默认值：None（自动推断）
                
            persist_dir (str, 可选)
                知识库持久化存储目录。存储向量、分片、索引和元数据。
                默认值："./kb_store"
                
            embedding_model (str, 可选)
                嵌入模型名称。支持 HuggingFace 模型标识符。
                默认值："Qwen/Qwen3-Embedding-0.6B"
                示例："sentence-transformers/all-MiniLM-L6-v2"
                
            reranker_model (str, 可选)
                重排序模型名称。用于精排搜索结果。
                默认值："Qwen/Qwen3-Reranker-0.6B"
                
            device (str, 可选)
                推理设备选择。可为 "cuda"、"cpu" 或 "auto"。
                当为 "auto" 时，如果 GPU 可用则使用 CUDA，否则使用 CPU。
                默认值："auto"（自动选择）
                
            local_files_only (bool, 可选)
                是否仅使用本地模型文件。为 True 时不会从网络下载模型。
                默认值：True（仅本地）
                
            chunk_size (int, 可选)
                文本分块大小（字符数）。文档会被分割成此大小的文本块。
                默认值：800
                范围：[100, ∞)
                
            chunk_overlap (int, 可选)
                分块之间的重叠字符数。用于保证分块之间的上下文连贯性。
                默认值：120
                范围：[0, ∞)
        
        配置文件支持：
            通过项目根目录的 config.json 文件配置所有参数，或通过环境变量：
            - KB_EMBED_MODEL: 嵌入模型
            - KB_RERANK_MODEL: 重排序模型
            - KB_MODEL_CACHE_DIR: 模型缓存目录
            - LM_STUDIO_BASE_URL: LM Studio 服务地址
            - LM_STUDIO_API_KEY: LM Studio API 密钥
        """
        config = self._load_project_config()
        kb_cfg = config.get("knowledge_base", {})
        storage_cfg = kb_cfg.get("storage", {}) if isinstance(kb_cfg.get("storage"), dict) else {}
        vector_backend_specified = ("vector_backend" in storage_cfg) or ("vector_backend" in kb_cfg)
        embedding_cfg = (
            kb_cfg.get("embedding", {}) if isinstance(kb_cfg.get("embedding"), dict) else {}
        )
        rerank_cfg = kb_cfg.get("rerank", {}) if isinstance(kb_cfg.get("rerank"), dict) else {}
        lm_cfg = kb_cfg.get("lm_studio", {}) if isinstance(kb_cfg.get("lm_studio"), dict) else {}
        chat_cfg = kb_cfg.get("chat", {}) if isinstance(kb_cfg.get("chat"), dict) else {}
        chunk_cfg = kb_cfg.get("chunking", {}) if isinstance(kb_cfg.get("chunking"), dict) else {}
        memory_cfg = kb_cfg.get("memory", {}) if isinstance(kb_cfg.get("memory"), dict) else {}
        search_cfg = config.get("search", {}) if isinstance(config.get("search"), dict) else {}
        retrieval_cfg = (
            kb_cfg.get("retrieval", {}) if isinstance(kb_cfg.get("retrieval"), dict) else {}
        )
        project_root = self._resolve_project_root()

        cfg_persist_dir = storage_cfg.get("persist_dir", kb_cfg.get("persist_dir", "./kb_store"))
        cfg_model_cache_dir = storage_cfg.get("model_cache_dir", kb_cfg.get("model_cache_dir"))
        cfg_vector_backend = storage_cfg.get("vector_backend", kb_cfg.get("vector_backend", "faiss"))
        cfg_cleanup_legacy_index_on_migrate = storage_cfg.get(
            "cleanup_legacy_index_on_migrate",
            kb_cfg.get("cleanup_legacy_index_on_migrate", False),
        )
        cfg_embed = embedding_cfg.get(
            "model", kb_cfg.get("embedding_model", "Qwen/Qwen3-Embedding-0.6B")
        )
        cfg_rerank = rerank_cfg.get(
            "model", kb_cfg.get("reranker_model", "Qwen/Qwen3-Reranker-0.6B")
        )
        cfg_dimension = embedding_cfg.get("dimension", kb_cfg.get("dimension"))
        cfg_device = embedding_cfg.get("device", kb_cfg.get("device", "auto"))
        cfg_local_only = embedding_cfg.get(
            "local_files_only", kb_cfg.get("local_files_only", True)
        )
        cfg_auto_download_missing = kb_cfg.get("auto_download_missing_models", True)
        cfg_lm_base = lm_cfg.get("base_url", kb_cfg.get("lm_studio_base_url"))
        cfg_lm_api_key = lm_cfg.get("api_key", kb_cfg.get("lm_studio_api_key"))
        cfg_lm_timeout = lm_cfg.get("timeout", kb_cfg.get("lm_studio_timeout", 30))
        cfg_lm_chat_model = lm_cfg.get("chat_model", kb_cfg.get("chat_model"))
        cfg_chat_model = chat_cfg.get("model", kb_cfg.get("chat_model", cfg_lm_chat_model))
        cfg_chat_use_lm = chat_cfg.get("use_lm_studio", kb_cfg.get("use_lm_studio_chat", True))
        cfg_chat_local_only = chat_cfg.get(
            "local_files_only", kb_cfg.get("chat_local_files_only", cfg_local_only)
        )
        cfg_chat_temperature = chat_cfg.get("temperature", kb_cfg.get("chat_temperature", 0.2))
        cfg_chat_max_tokens = chat_cfg.get("max_tokens", kb_cfg.get("chat_max_tokens", 512))
        cfg_lm_embed = embedding_cfg.get(
            "use_lm_studio", kb_cfg.get("use_lm_studio_embeddings")
        )
        cfg_lm_rerank = rerank_cfg.get("use_lm_studio", kb_cfg.get("use_lm_studio_rerank"))
        cfg_chunk_size = chunk_cfg.get("size", kb_cfg.get("chunk_size", 800))
        cfg_chunk_overlap = chunk_cfg.get("overlap", kb_cfg.get("chunk_overlap", 120))
        cfg_default_k = search_cfg.get("default_k", kb_cfg.get("default_k", 2))
        cfg_max_search_results = kb_cfg.get(
            "max_search_results", search_cfg.get("max_search_results", 2)
        )
        cfg_candidate_multiplier = retrieval_cfg.get(
            "candidate_multiplier", kb_cfg.get("candidate_multiplier", 8)
        )
        cfg_min_candidates = retrieval_cfg.get(
            "min_candidates", kb_cfg.get("min_candidates", 30)
        )
        cfg_embed_weight = retrieval_cfg.get("embed_weight", kb_cfg.get("embed_weight", 0.35))
        cfg_rerank_weight = retrieval_cfg.get(
            "rerank_weight", kb_cfg.get("rerank_weight", 0.65)
        )
        cfg_release_gpu_cache = memory_cfg.get("release_gpu_cache", False)
        cfg_unload_idle_seconds = memory_cfg.get("unload_models_idle_seconds", 0)

        persist_path = Path(persist_dir or cfg_persist_dir)
        if not persist_path.is_absolute():
            persist_path = project_root / persist_path
        self.persist_dir = persist_path.resolve()
        model_cache_path = (os.getenv("KB_MODEL_CACHE_DIR") or cfg_model_cache_dir or "").strip()
        if model_cache_path:
            cache_path = Path(model_cache_path)
            if not cache_path.is_absolute():
                cache_path = project_root / cache_path
            self.model_cache_dir = cache_path.resolve()
        else:
            self.model_cache_dir = (self.persist_dir / "hf_cache").resolve()
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.persist_dir / "meta.json"
        self.chunks_path = self.persist_dir / "chunks.jsonl"
        self.embeddings_path = self.persist_dir / "embeddings.npy"
        self.vector_backend = str(cfg_vector_backend or "faiss").strip().lower()
        if self.vector_backend not in {"faiss", "zvec", "numpy"}:
            logger.warning("Unknown vector backend '%s', fallback to faiss", self.vector_backend)
            self.vector_backend = "faiss"
        self._vector_backend_specified = bool(vector_backend_specified)
        self.cleanup_legacy_index_on_migrate = bool(cfg_cleanup_legacy_index_on_migrate)
        self.index_path = self._index_path_for_backend(self.vector_backend)

        self.embedding_model_name = embedding_model or os.getenv("KB_EMBED_MODEL", cfg_embed)
        self.reranker_model_name = reranker_model or os.getenv("KB_RERANK_MODEL", cfg_rerank)
        self.reranker_model_name = self._normalize_reranker_model_name(self.reranker_model_name)
        if dimension is not None:
            self.dimension = int(dimension)
        elif cfg_dimension is not None:
            self.dimension = int(cfg_dimension)
        else:
            self.dimension = None

        self.chunk_size = max(100, int(chunk_size if chunk_size is not None else cfg_chunk_size))
        self.chunk_overlap = max(
            0, int(chunk_overlap if chunk_overlap is not None else cfg_chunk_overlap)
        )
        self.default_k = max(1, int(cfg_default_k))
        self.max_search_results = max(1, int(cfg_max_search_results))
        self.candidate_multiplier = max(1, int(cfg_candidate_multiplier))
        self.min_candidates = max(1, int(cfg_min_candidates))
        self.embed_weight = float(cfg_embed_weight)
        self.rerank_weight = float(cfg_rerank_weight)
        total_weight = self.embed_weight + self.rerank_weight
        if total_weight <= 0:
            self.embed_weight, self.rerank_weight = 0.35, 0.65
        else:
            self.embed_weight /= total_weight
            self.rerank_weight /= total_weight

        if local_files_only is None:
            if isinstance(cfg_local_only, bool):
                self.local_files_only = cfg_local_only
            else:
                local_only_env = os.getenv("KB_LOCAL_FILES_ONLY", "").strip().lower()
                if local_only_env:
                    self.local_files_only = local_only_env in {"1", "true", "yes", "on"}
                else:
                    # 默认允许联网下载（改为 False）
                    self.local_files_only = False
        else:
            self.local_files_only = bool(local_files_only)

        if isinstance(cfg_auto_download_missing, bool):
            self.auto_download_missing_models = cfg_auto_download_missing
        else:
            self.auto_download_missing_models = True
        
        # 调试：输出 local_files_only 的值
        logger.info("KnowledgeBase initialized: local_files_only=%s (from config=%s)", 
                    self.local_files_only, cfg_local_only)
        self._configure_hf_offline_mode()

        # Detect AMD ROCm availability (torch ROCm exposes cuda API via HIP)
        def _torch_has_rocm() -> bool:
            try:
                return bool(getattr(torch.version, "hip", None))
            except Exception:
                return False

        _rocm_available = _torch_has_rocm() and torch.cuda.is_available()
        _cuda_available = torch.cuda.is_available() and not _rocm_available

        if device:
            self.device = device
        else:
            if str(cfg_device).lower() == "auto":
                if _cuda_available or _rocm_available:
                    self.device = "cuda"  # both NVIDIA CUDA and AMD ROCm surface as "cuda"
                else:
                    self.device = "cpu"
            else:
                self.device = str(cfg_device)

        logger.info(
            "Torch runtime: version=%s cuda_build=%s cuda_available=%s rocm_build=%s device_count=%s",
            torch.__version__,
            torch.version.cuda,
            torch.cuda.is_available(),
            getattr(torch.version, "hip", None),
            torch.cuda.device_count(),
        )
        if str(cfg_device).lower() == "auto" and self.device == "cpu":
            if torch.version.cuda is None and getattr(torch.version, "hip", None) is None:
                logger.warning(
                    "No GPU available: current torch build is CPU-only (%s). "
                    "For NVIDIA: pip install --force-reinstall torch==2.2.2 --index-url https://download.pytorch.org/whl/cu121 ; "
                    "For AMD ROCm: pip install --force-reinstall torch==2.2.2 --index-url https://download.pytorch.org/whl/rocm6.0",
                    torch.__version__,
                )
        logger.info(
            "Inference device selected: %s (cuda_available=%s rocm=%s)",
            self.device,
            torch.cuda.is_available(),
            _rocm_available,
        )

        lm_base = (os.getenv("LM_STUDIO_BASE_URL") or cfg_lm_base or "").strip()
        self.lm_studio_base_url = lm_base or None
        lm_key = (os.getenv("LM_STUDIO_API_KEY") or cfg_lm_api_key or "").strip()
        self.lm_studio_api_key = lm_key or None
        chat_model = (os.getenv("KB_CHAT_MODEL") or cfg_lm_chat_model or "").strip()
        if not chat_model:
            chat_model = str(cfg_chat_model or "").strip()
        self.chat_model_name = chat_model or None
        timeout_env = os.getenv("LM_STUDIO_TIMEOUT", "").strip()
        if timeout_env:
            try:
                self.lm_studio_timeout = float(timeout_env)
            except Exception:
                self.lm_studio_timeout = float(cfg_lm_timeout or 30)
        else:
            self.lm_studio_timeout = float(cfg_lm_timeout or 30)
        if isinstance(cfg_lm_embed, bool):
            self.use_lm_studio_embeddings = cfg_lm_embed
        else:
            self.use_lm_studio_embeddings = False
        if isinstance(cfg_lm_rerank, bool):
            self.use_lm_studio_rerank = cfg_lm_rerank
        else:
            self.use_lm_studio_rerank = False
        if isinstance(cfg_chat_use_lm, bool):
            self.use_lm_studio_chat = cfg_chat_use_lm
        else:
            self.use_lm_studio_chat = True
        if isinstance(cfg_chat_local_only, bool):
            self.chat_local_files_only = cfg_chat_local_only
        else:
            self.chat_local_files_only = self.local_files_only
        self.chat_temperature = float(cfg_chat_temperature)
        self.chat_max_tokens = max(1, int(cfg_chat_max_tokens))

        self._embed_tokenizer = None
        self._embed_model = None
        self._rerank_tokenizer = None
        self._rerank_model = None
        self._lm_client = None
        if self.lm_studio_base_url:
            self._lm_client = LmStudioClient(
                self.lm_studio_base_url,
                api_key=self.lm_studio_api_key,
                timeout=self.lm_studio_timeout,
            )
        self._chat_backend = ChatModel(
            device=self.device,
            model_cache_dir=self.model_cache_dir,
            use_lm_studio=self.use_lm_studio_chat,
            lm_client=self._lm_client,
            lm_base_url=self.lm_studio_base_url,
            lm_api_key=self.lm_studio_api_key,
            lm_timeout=self.lm_studio_timeout,
            local_files_only=self.chat_local_files_only,
            default_temperature=self.chat_temperature,
            default_max_tokens=self.chat_max_tokens,
        )
        # 传递 OCR 配置给文档解析器
        ocr_cfg = kb_cfg.get("ocr", {}) if isinstance(kb_cfg.get("ocr"), dict) else {}
        self._document_parser = KnowledgeBaseDocumentParser(
            logger=logger,
            model_cache_dir=self.model_cache_dir,
            ocr_config=ocr_cfg,
        )

        self._chunks: List[_Chunk] = []
        self._embeddings = np.zeros((0, 1), dtype=np.float32)
        self._index = None
        self._faiss_gpu_resources = None
        self._faiss_use_gpu = self._should_use_faiss_gpu()
        self.release_gpu_cache = bool(cfg_release_gpu_cache)
        try:
            self.unload_models_idle_seconds = max(0, int(cfg_unload_idle_seconds))
        except Exception:
            self.unload_models_idle_seconds = 0
        self._model_last_used: Dict[str, float] = {}
        self._active_lock = threading.Lock()
        self._active_requests = 0
        logger.info(
            "Vector backend runtime: backend=%s faiss_available=%s zvec_available=%s faiss_gpu_enabled=%s",
            self.vector_backend,
            bool(faiss is not None),
            bool(zvec is not None),
            self._faiss_use_gpu,
        )

        self._load()
        logger.info(
            "KnowledgeBase ready: persist_dir=%s model_cache_dir=%s embed=%s rerank=%s chat=%s",
            self.persist_dir,
            self.model_cache_dir,
            self.embedding_model_name,
            self.reranker_model_name,
            self.chat_model_name,
        )
        logger.info(
            "KnowledgeBase loaded from store: documents=%s chunks=%s",
            len({c.filename for c in self._chunks}),
            len(self._chunks),
        )
        if self._chunks:
            by_doc: Dict[str, int] = {}
            for chunk in self._chunks:
                by_doc[chunk.filename] = by_doc.get(chunk.filename, 0) + 1
            doc_list = [f"{name}({count})" for name, count in sorted(by_doc.items(), key=lambda x: x[0].lower())]
            logger.info("KnowledgeBase documents: %s", ", ".join(doc_list))

        # 启动后台线程定时释放空闲模型

        def _auto_release_idle_models(self):
            while True:
                try:
                    # logger.info("[定时任务] 执行 release_idle_gpu 检查模型空闲状态并尝试释放...")
                    self.release_idle_gpu()
                except Exception as e:
                    logger.warning("Auto release idle models failed: %s", e)
                time.sleep(10)

        threading.Thread(target=_auto_release_idle_models, args=(self,), daemon=True).start()

    @staticmethod
    def _normalize_reranker_model_name(name: str | None) -> str:
        model_name = (name or "").strip()
        if not model_name:
            return model_name
        # Compatibility for common typo: "...Rerank-..." -> "...Reranker-..."
        if "Rerank-" in model_name and "Reranker-" not in model_name:
            return model_name.replace("Rerank-", "Reranker-")
        return model_name

    def _configure_hf_offline_mode(self) -> None:
        if not self.local_files_only:
            # 确保在线模式时清除可能存在的离线标志
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            os.environ.pop("HF_DATASETS_OFFLINE", None)
            return
        # Keep HuggingFace stack fully offline when local cache mode is enabled.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    @staticmethod
    def _force_hf_online_mode() -> None:
        # Some libs cache offline flags at import time; clear env and patch constants.
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
        os.environ.pop("HF_DATASETS_OFFLINE", None)
        try:
            import huggingface_hub.constants as hf_constants  # type: ignore

            hf_constants.HF_HUB_OFFLINE = False
        except Exception:
            pass

    def _download_model_snapshot(self, model_name: str) -> str:
        self._force_hf_online_mode()
        endpoint = (
            os.environ.get("HF_HUB_ENDPOINT")
            or os.environ.get("HF_ENDPOINT")
            or "https://hf-mirror.com"
        )
        os.environ["HF_ENDPOINT"] = endpoint
        os.environ["HF_HUB_ENDPOINT"] = endpoint
        try:
            from huggingface_hub import snapshot_download
        except Exception as exc:
            raise RuntimeError("huggingface_hub is required for auto-download fallback") from exc

        logger.info("Downloading model snapshot: %s via %s", model_name, endpoint)
        local_dir = snapshot_download(
            repo_id=model_name,
            cache_dir=str(self.model_cache_dir),
            local_files_only=False,
            endpoint=endpoint,
        )
        logger.info("Model snapshot downloaded: %s -> %s", model_name, local_dir)
        return str(local_dir)
        try:
            import transformers.utils.hub as tf_hub_utils  # type: ignore

            if hasattr(tf_hub_utils, "_is_offline_mode"):
                tf_hub_utils._is_offline_mode = False
        except Exception:
            pass

    @staticmethod
    def _is_local_model_missing_error(exc: Exception) -> bool:
        exc_type = type(exc).__name__.lower()
        if "notfound" in exc_type or "localentry" in exc_type:
            return True
        message = str(exc).lower()
        missing_markers = (
            "not found in local",
            "could not find",
            "couldn't find",
            "can't find",
            "no such file or directory",
            "is not the path to a directory containing",
            "does not appear to have a file named",
            "cannot find the requested files",
            "cannot find requested files",
        )
        return any(marker in message for marker in missing_markers)

    @staticmethod
    def _is_fast_tokenizer_parse_error(exc: Exception) -> bool:
        message = str(exc).lower()
        markers = (
            "modelwrapper",
            "tokenizerfast.from_file",
            "data did not match any variant",
            "untagged enum",
        )
        return any(marker in message for marker in markers)

    @staticmethod
    def _normalize_filename(name: str | None) -> str:
        return Path(str(name or "").strip()).name

    def _resolve_cached_model_path(self, model_name: str | None) -> Path | None:
        model_ref = str(model_name or "").strip()
        if not model_ref:
            return None

        direct_path = Path(model_ref)
        if direct_path.exists():
            return direct_path.resolve()

        repo_dir = self.model_cache_dir / f"models--{model_ref.replace('/', '--')}"
        if not repo_dir.exists():
            return None

        snapshots_dir = repo_dir / "snapshots"
        refs_main = repo_dir / "refs" / "main"
        if refs_main.exists():
            try:
                snapshot_name = refs_main.read_text(encoding="utf-8").strip()
                if snapshot_name:
                    snapshot_path = snapshots_dir / snapshot_name
                    if snapshot_path.exists():
                        return snapshot_path.resolve()
            except Exception:
                pass

        if snapshots_dir.exists():
            try:
                snapshot_candidates = [p for p in snapshots_dir.iterdir() if p.is_dir()]
                snapshot_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                if snapshot_candidates:
                    return snapshot_candidates[0].resolve()
            except Exception:
                pass

        if (repo_dir / "config.json").exists() or (repo_dir / "tokenizer_config.json").exists():
            return repo_dir.resolve()
        return None

    @staticmethod
    def _filename_key(name: str | None) -> str:
        return KnowledgeBase._normalize_filename(name).lower()

    @staticmethod
    def _load_project_config() -> Dict[str, Any]:
        try:
            from .shared.config_paths import load_project_config
        except ImportError:  # pragma: no cover
            from shared.config_paths import load_project_config
        return load_project_config()

    @staticmethod
    def _resolve_project_root() -> Path:
        try:
            from .shared.config_paths import resolve_project_root
        except ImportError:  # pragma: no cover
            from shared.config_paths import resolve_project_root
        return resolve_project_root()

    @staticmethod
    def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
        if vectors.size == 0:
            return vectors.astype(np.float32, copy=False)
        vectors = vectors.astype(np.float32, copy=False)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-12, None)
        return vectors / norms

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    def _save(self) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "embedding_model": self.embedding_model_name,
            "reranker_model": self.reranker_model_name,
            "dimension": self.dimension,
            "vector_backend": self.vector_backend,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "candidate_multiplier": self.candidate_multiplier,
            "min_candidates": self.min_candidates,
            "embed_weight": self.embed_weight,
            "rerank_weight": self.rerank_weight,
        }
        self.meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with self.chunks_path.open("w", encoding="utf-8") as f:
            for chunk in self._chunks:
                f.write(
                    json.dumps(
                        {"filename": chunk.filename, "text": chunk.text},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        np.save(self.embeddings_path, self._embeddings)
        if self._index is None:
            return
        if self.vector_backend == "zvec" and zvec is not None:
            try:
                self._save_zvec_index(self._index)
                return
            except Exception as exc:
                logger.warning("Save zvec index failed, fallback to faiss persistence path: %s", exc)
        if faiss is not None:
            idx_to_save = self._index
            # GPU index cannot be serialized directly; persist as CPU index.
            if self._faiss_use_gpu and hasattr(faiss, "index_gpu_to_cpu"):
                idx_to_save = faiss.index_gpu_to_cpu(self._index)
            try:
                faiss.write_index(idx_to_save, str(self.index_path))
            except Exception as exc:
                logger.warning("Save faiss index failed: %s", exc)

    def _index_path_for_backend(self, backend: str) -> Path:
        suffix = "zvec" if str(backend).strip().lower() == "zvec" else "faiss"
        return self.persist_dir / f"index.{suffix}"

    def _load(self) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        configured_backend = self.vector_backend
        configured_path = self._index_path_for_backend(configured_backend)
        meta_backend = ""

        if self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            if not self.dimension and meta.get("dimension"):
                self.dimension = int(meta["dimension"])
            meta_backend = str(meta.get("vector_backend") or "").strip().lower()
            if meta_backend in {"faiss", "zvec", "numpy"}:
                # If user explicitly configured backend in config, keep config value;
                # otherwise, continue using the backend from persisted metadata.
                if not self._vector_backend_specified:
                    self.vector_backend = meta_backend
                    self.index_path = self._index_path_for_backend(self.vector_backend)

        switched_backend = bool(
            meta_backend in {"faiss", "zvec", "numpy"}
            and self.vector_backend in {"faiss", "zvec", "numpy"}
            and meta_backend != self.vector_backend
        )
        legacy_index_path = self._index_path_for_backend(meta_backend) if switched_backend else None
        if switched_backend:
            logger.info(
                "Vector backend switched: from=%s to=%s, index will be auto-migrated",
                meta_backend,
                self.vector_backend,
            )
            self.index_path = configured_path

        if self.chunks_path.exists():
            chunks = []
            with self.chunks_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    chunks.append(
                        _Chunk(
                            filename=self._normalize_filename(str(obj.get("filename", ""))),
                            text=str(obj.get("text", "")),
                        )
                    )
            self._chunks = chunks

        if self.embeddings_path.exists():
            emb = np.load(self.embeddings_path)
            if emb.ndim == 2:
                self._embeddings = emb.astype(np.float32, copy=False)
                if self._embeddings.shape[0] > 0:
                    self.dimension = int(self._embeddings.shape[1])

        if len(self._chunks) == 0:
            if self.dimension is None:
                self.dimension = 1024
            self._chunks = []
            self._embeddings = np.zeros((0, self.dimension), dtype=np.float32)
            self._index = None
            self._save()
            return

        if self._embeddings.ndim != 2 or len(self._chunks) != self._embeddings.shape[0]:
            logger.info(
                "Embeddings missing/mismatch on startup, rebuilding from chunks: chunks=%s emb_shape=%s",
                len(self._chunks),
                tuple(self._embeddings.shape) if hasattr(self._embeddings, "shape") else None,
            )
            self._rebuild_embeddings_from_chunks()
            self._save()
            return

        if switched_backend:
            self._rebuild_index()
            self._save()
            logger.info(
                "Vector index migration finished: from=%s to=%s index=%s",
                meta_backend,
                self.vector_backend,
                self.index_path,
            )
            if (
                self.cleanup_legacy_index_on_migrate
                and legacy_index_path is not None
                and legacy_index_path != self.index_path
                and legacy_index_path.exists()
            ):
                try:
                    if legacy_index_path.is_dir():
                        shutil.rmtree(legacy_index_path)
                    else:
                        legacy_index_path.unlink()
                    logger.info("Legacy index removed after migration: %s", legacy_index_path)
                except Exception as exc:
                    logger.warning("Failed to remove legacy index '%s': %s", legacy_index_path, exc)
            return

        if self.index_path.exists():
            loaded = False
            if self.vector_backend == "zvec" and zvec is not None:
                try:
                    self._index = self._load_zvec_index()
                    loaded = self._index is not None
                except Exception as exc:
                    logger.warning("Load zvec index failed, will rebuild: %s", exc)
            if not loaded and faiss is not None:
                try:
                    cpu_index = faiss.read_index(str(self.index_path))
                    self._index = self._to_faiss_gpu_index(cpu_index)
                    loaded = True
                except Exception:
                    loaded = False
            if not loaded:
                self._rebuild_index()
        else:
            self._rebuild_index()

    def _rebuild_embeddings_from_chunks(self) -> None:
        texts = [c.text for c in self._chunks]
        if not texts:
            dim = int(self.dimension or 1024)
            self._embeddings = np.zeros((0, dim), dtype=np.float32)
            self.dimension = dim
            self._rebuild_index()
            return
        vecs = self._embed_texts(texts)
        if vecs.ndim != 2 or vecs.shape[0] != len(texts):
            raise RuntimeError("Embedding rebuild failed: shape mismatch")
        self._embeddings = vecs.astype(np.float32, copy=False)
        self.dimension = int(self._embeddings.shape[1])
        self._rebuild_index()

    def _ensure_embed_model(self) -> None:
        if self._embed_model is not None and self._embed_tokenizer is not None:
            return
        try:
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:
            raise RuntimeError(
                "Failed to import transformers stack. "
                "Install missing deps (e.g. certifi, transformers, huggingface_hub)."
            ) from exc
        
        # 设置 Hugging Face 镜像（支持国内访问）
        endpoint = (
            os.environ.get("HF_HUB_ENDPOINT")
            or os.environ.get("HF_ENDPOINT")
            or "https://hf-mirror.com"
        )
        os.environ["HF_ENDPOINT"] = endpoint
        os.environ["HF_HUB_ENDPOINT"] = endpoint
        
        logger.info(
            "Loading embedding model(local-first): %s (auto_download_missing_models=%s, mirror=%s)",
            self.embedding_model_name,
            self.auto_download_missing_models,
            os.environ.get("HF_HUB_ENDPOINT"),
        )

        local_model_path = self._resolve_cached_model_path(self.embedding_model_name)
        if local_model_path is not None:
            logger.info("Embedding local snapshot resolved: %s -> %s", self.embedding_model_name, local_model_path)
        else:
            logger.info("Embedding local snapshot not found under cache_dir=%s for model=%s", self.model_cache_dir, self.embedding_model_name)

        kwargs = dict(
            trust_remote_code=True,
            cache_dir=str(self.model_cache_dir),
        )

        def _load_embed_tokenizer(model_ref: str) -> Any:
            try:
                return AutoTokenizer.from_pretrained(
                    model_ref,
                    local_files_only=True,
                    **kwargs,
                )
            except Exception as tok_exc:
                if not self._is_fast_tokenizer_parse_error(tok_exc):
                    raise
                logger.warning(
                    "Embedding fast tokenizer load failed, fallback to slow tokenizer: %s",
                    tok_exc,
                )
                return AutoTokenizer.from_pretrained(
                    model_ref,
                    local_files_only=True,
                    use_fast=False,
                    **kwargs,
                )

        local_ref = str(local_model_path) if local_model_path is not None else self.embedding_model_name

        try:
            self._embed_tokenizer = _load_embed_tokenizer(local_ref)
            self._embed_model = AutoModel.from_pretrained(
                local_ref,
                local_files_only=True,
                **kwargs,
            )
            logger.info("Embedding model loaded from local cache: %s", local_ref)
        except Exception as local_exc:
            if (not self.auto_download_missing_models) or (not self._is_local_model_missing_error(local_exc)):
                raise
            logger.warning(
                "Embedding model not found or incomplete in local cache, will auto-download: %s",
                local_exc,
            )
            local_snapshot = self._download_model_snapshot(self.embedding_model_name)
            self._embed_tokenizer = _load_embed_tokenizer(local_snapshot)
            self._embed_model = AutoModel.from_pretrained(
                local_snapshot,
                local_files_only=True,
                **kwargs,
            )
            logger.info("Embedding model downloaded and loaded: %s", self.embedding_model_name)
        self._embed_model.to(self.device)
        self._embed_model.eval()

    def _ensure_reranker_model(self) -> None:
        if self._rerank_model is not None and self._rerank_tokenizer is not None:
            return
        try:
            from transformers import (
                AutoModel,
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to import transformers stack. "
                "Install missing deps (e.g. certifi, transformers, huggingface_hub)."
            ) from exc
        
        # 设置 Hugging Face 镜像（支持国内访问）
        endpoint = (
            os.environ.get("HF_HUB_ENDPOINT")
            or os.environ.get("HF_ENDPOINT")
            or "https://hf-mirror.com"
        )
        os.environ["HF_ENDPOINT"] = endpoint
        os.environ["HF_HUB_ENDPOINT"] = endpoint
        
        logger.info(
            "Loading reranker model(local-first): %s (auto_download_missing_models=%s, mirror=%s)",
            self.reranker_model_name,
            self.auto_download_missing_models,
            os.environ.get("HF_HUB_ENDPOINT"),
        )

        local_model_path = self._resolve_cached_model_path(self.reranker_model_name)
        if local_model_path is not None:
            logger.info("Reranker local snapshot resolved: %s -> %s", self.reranker_model_name, local_model_path)
        else:
            logger.info("Reranker local snapshot not found under cache_dir=%s for model=%s", self.model_cache_dir, self.reranker_model_name)

        kwargs = dict(
            trust_remote_code=True,
            cache_dir=str(self.model_cache_dir),
        )

        def _load_rerank_tokenizer(model_ref: str) -> Any:
            try:
                return AutoTokenizer.from_pretrained(
                    model_ref,
                    local_files_only=True,
                    **kwargs,
                )
            except Exception as tok_exc:
                if not self._is_fast_tokenizer_parse_error(tok_exc):
                    raise
                logger.warning(
                    "Reranker fast tokenizer load failed, fallback to slow tokenizer: %s",
                    tok_exc,
                )
                return AutoTokenizer.from_pretrained(
                    model_ref,
                    local_files_only=True,
                    use_fast=False,
                    **kwargs,
                )

        local_ref = str(local_model_path) if local_model_path is not None else self.reranker_model_name

        try:
            self._rerank_tokenizer = _load_rerank_tokenizer(local_ref)
            try:
                # Prefer model's native implementation (often provides compute_score for reranker).
                self._rerank_model = AutoModel.from_pretrained(
                    local_ref,
                    local_files_only=True,
                    **kwargs,
                )
            except Exception:
                self._rerank_model = AutoModelForSequenceClassification.from_pretrained(
                    local_ref,
                    local_files_only=True,
                    **kwargs,
                )
            logger.info("Reranker model loaded from local cache: %s", local_ref)
        except Exception as local_exc:
            if (not self.auto_download_missing_models) or (not self._is_local_model_missing_error(local_exc)):
                raise
            logger.warning(
                "Reranker model not found or incomplete in local cache, will auto-download: %s",
                local_exc,
            )
            local_snapshot = self._download_model_snapshot(self.reranker_model_name)
            self._rerank_tokenizer = _load_rerank_tokenizer(local_snapshot)
            try:
                self._rerank_model = AutoModel.from_pretrained(
                    local_snapshot,
                    local_files_only=True,
                    **kwargs,
                )
            except Exception:
                self._rerank_model = AutoModelForSequenceClassification.from_pretrained(
                    local_snapshot,
                    local_files_only=True,
                    **kwargs,
                )
            logger.info("Reranker model downloaded and loaded: %s", self.reranker_model_name)
        self._rerank_model.to(self.device)
        self._rerank_model.eval()
        logger.info(
            "Reranker model loaded: %s (compute_score=%s)",
            self.reranker_model_name,
            hasattr(self._rerank_model, "compute_score"),
        )

    def chat_once(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        与聊天模型进行单轮对话（阻塞式，等待完整响应）。
        
        需要事先配置聊天模型（通常为 LM Studio 或本地大模型服务）。
        
        参数说明：
            messages (Sequence[Dict[str, Any]])
                对话历史消息列表。每条消息遵循 OpenAI Chat Completions API 格式：
                [
                    {"role": "system", "content": "You are a helpful assistant..."},
                    {"role": "user", "content": "What is Python?"},
                    {"role": "assistant", "content": "Python is..."},
                    {"role": "user", "content": "Tell me more"},
                ]
                
            model (str, 可选)
                覆盖默认配置的模型名称。如果为 None，使用 self.chat_model_name。
                示例："gpt-3.5-turbo"、"mistral"、"llama2"
                
            temperature (float, 可选)
                生成多样性控制参数。范围：[0.0, 2.0]
                - 0.0：完全确定性，重复相同内容
                - 1.0：默认平衡
                - 2.0：最大多样性，可能包含错误
                默认值：None（使用模型默认值或系统配置 0.2）
                
            max_tokens (int, 可选)
                生成的最大 token 数。范围：[1, 模型最大值]
                默认值：None（使用系统配置或模型默认值）
                
        返回值：
            str
                模型的完整响应文本。
        
        异常处理：
            RuntimeError
                - 未配置聊天模型
                - 模型服务不可用或连接失败
            ValueError
                - messages 格式错误
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> messages = [
            ...     {"role": "user", "content": "What is the capital of France?"}
            ... ]
            >>> response = kb.chat_once(messages)
            >>> print(response)
            
        多轮对话示例：
            >>> messages = [
            ...     {"role": "user", "content": "Hello, what's 2+2?"},
            ... ]
            >>> response = kb.chat_once(messages)
            >>> print(f"Assistant: {response}")
            >>> 
            >>> # 继续对话
            >>> messages.append({"role": "assistant", "content": response})
            >>> messages.append({"role": "user", "content": "What about 3+3?"})
            >>> response2 = kb.chat_once(messages)
            >>> print(f"Assistant: {response2}")
        """
        chosen_model = str(model or self.chat_model_name or "").strip()
        if not chosen_model:
            raise RuntimeError("No chat model configured")
        if not self.use_lm_studio_chat:
            self._touch_model("chat")
        return self._chat_backend.chat_once(
            messages=messages,
            model=chosen_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_stream(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Sequence[str]:
        """
        与聊天模型进行流式对话（实时流传输响应）。
        
        返回一个可迭代的文本块序列，模型生成的内容实时流回而不是等待完整响应。
        适合长文本生成或需要实时反馈的场景。
        
        参数说明：
            messages (Sequence[Dict[str, Any]])
                对话历史消息列表。格式同 chat_once()。参见上方说明。
                
            model (str, 可选)
                覆盖默认配置的模型名称。默认为 None（使用 self.chat_model_name）。
                
            temperature (float, 可选)
                生成多样性控制参数。范围：[0.0, 2.0]。默认为 None。
                
            max_tokens (int, 可选)
                生成的最大 token 数。默认为 None。
                
        返回值：
            Sequence[str]
                可迭代的文本块序列。每次迭代返回模型生成的部分文本。
                可用于逐步显示模型输出、长文本处理等。
        
        异常处理：
            RuntimeError: 未配置聊天模型或连接失败
            ValueError: messages 格式错误
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> messages = [
            ...     {"role": "user", "content": "Write a short story about a robot"}
            ... ]
            >>> 
            >>> # 实时显示响应
            >>> for chunk in kb.chat_stream(messages):
            ...     print(chunk, end="", flush=True)
            >>> print()  # 换行
            
        Web 应用中的用法（假设使用 Flask）：
            >>> from flask import Flask, Response
            >>> app = Flask(__name__)
            >>> kb = KnowledgeBase()
            >>> 
            >>> @app.route("/chat-stream", methods=["POST"])
            >>> def chat_stream_endpoint():
            ...     messages = request.json.get("messages", [])
            ...     def generate():
            ...         for chunk in kb.chat_stream(messages):
            ...             yield f"data: {chunk}\\n\\n"
            ...     return Response(generate(), mimetype="text/event-stream")
            
        性能特性：
            - 降低首字节延迟：不需要等待完整生成
            - 降低内存使用：流式处理不需缓存整个响应
            - 更佳用户体验：实时反馈而非等待
        """
        chosen_model = str(model or self.chat_model_name or "").strip()
        if not chosen_model:
            raise RuntimeError("No chat model configured")
        if not self.use_lm_studio_chat:
            self._touch_model("chat")
        return self._chat_backend.chat_stream(
            messages=messages,
            model=chosen_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _mean_pool(self, last_hidden_state: torch.Tensor, attention_mask: torch.Tensor):
        mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.shape).float()
        masked = last_hidden_state * mask
        summed = masked.sum(dim=1)
        denom = mask.sum(dim=1).clamp(min=1e-12)
        return summed / denom

    @staticmethod
    def _summarize_texts(texts: Sequence[str]) -> Dict[str, int]:
        count = len(texts)
        if count == 0:
            return {"count": 0, "avg_len": 0, "max_len": 0}
        lengths = [len(str(t or "")) for t in texts]
        total = sum(lengths)
        return {
            "count": count,
            "avg_len": int(total / max(1, count)),
            "max_len": max(lengths),
        }

    def _embed_texts(self, texts: Sequence[str], batch_size: int = 16) -> np.ndarray:
        summary = self._summarize_texts(texts)
        logger.info(
            "Embedding input: model=%s count=%s avg_len=%s max_len=%s use_lm_studio=%s",
            self.embedding_model_name,
            summary["count"],
            summary["avg_len"],
            summary["max_len"],
            self.use_lm_studio_embeddings,
        )
        if self.use_lm_studio_embeddings and self._lm_client is not None:
            vecs = self._lm_client.embed_texts(texts, model=self.embedding_model_name)
            if vecs.shape[0] > 0 and self.dimension is None:
                self.dimension = int(vecs.shape[1])
            logger.info(
                "Embedding output: model=%s vectors=%s dim=%s",
                self.embedding_model_name,
                vecs.shape[0],
                int(vecs.shape[1]) if vecs.ndim > 1 else 0,
            )
            return vecs
        self._ensure_embed_model()
        self._touch_model("embedding")
        all_vecs = []

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]

            if hasattr(self._embed_model, "encode"):
                vec = self._embed_model.encode(batch)
                vec = np.asarray(vec, dtype=np.float32)
                all_vecs.append(vec)
                continue

            encoded = self._embed_tokenizer(
                list(batch),
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

            with torch.no_grad():
                outputs = self._embed_model(**encoded)

            if hasattr(outputs, "last_hidden_state"):
                pooled = self._mean_pool(outputs.last_hidden_state, encoded["attention_mask"])
            elif hasattr(outputs, "pooler_output"):
                pooled = outputs.pooler_output
            else:
                pooled = outputs[0][:, 0, :]

            all_vecs.append(pooled.detach().cpu().numpy().astype(np.float32))

        vectors = np.vstack(all_vecs) if all_vecs else np.zeros((0, 1), dtype=np.float32)
        vectors = self._normalize_rows(vectors)
        if vectors.shape[0] > 0 and self.dimension is None:
            self.dimension = int(vectors.shape[1])
        logger.info(
            "Embedding output: model=%s vectors=%s dim=%s",
            self.embedding_model_name,
            vectors.shape[0],
            int(vectors.shape[1]) if vectors.ndim > 1 else 0,
        )
        return vectors

    def _rerank_scores(self, query: str, docs: Sequence[str], batch_size: int = 8) -> List[float]:
        summary = self._summarize_texts(docs)
        logger.info(
            "Rerank input: model=%s docs=%s avg_doc_len=%s max_doc_len=%s query_len=%s use_lm_studio=%s",
            self.reranker_model_name,
            summary["count"],
            summary["avg_len"],
            summary["max_len"],
            len(str(query or "")),
            self.use_lm_studio_rerank,
        )
        if (
            self.use_lm_studio_rerank
            and self._lm_client is not None
            and self._lm_client.rerank_supported is not False
        ):
            scores = self._lm_client.rerank_scores(
                query, docs, model=self.reranker_model_name
            )
            if scores is not None:
                logger.info(
                    "Rerank output: model=%s scores=%s min=%s max=%s",
                    self.reranker_model_name,
                    len(scores),
                    min(scores) if scores else None,
                    max(scores) if scores else None,
                )
                return scores
        self._ensure_reranker_model()
        self._touch_model("reranker")
        scores: List[float] = []

        if hasattr(self._rerank_model, "compute_score"):
            pairs = [[query, d] for d in docs]
            raw = self._rerank_model.compute_score(pairs)
            return [float(x) for x in raw]

        for start in range(0, len(docs), batch_size):
            batch_docs = list(docs[start : start + batch_size])
            queries = [query] * len(batch_docs)
            encoded = self._rerank_tokenizer(
                queries,
                batch_docs,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

            with torch.no_grad():
                outputs = self._rerank_model(**encoded)

            if hasattr(outputs, "logits"):
                raw_vals = outputs.logits
            elif hasattr(outputs, "last_hidden_state"):
                raw_vals = outputs.last_hidden_state
            elif isinstance(outputs, (tuple, list)) and len(outputs) > 0:
                raw_vals = outputs[0]
            else:
                raise RuntimeError("Unsupported reranker output format")

            vals = raw_vals if torch.is_tensor(raw_vals) else torch.as_tensor(raw_vals)
            if vals.ndim == 0:
                vals = vals.reshape(1)
            elif vals.ndim == 2:
                if vals.shape[1] > 1:
                    vals = vals[:, -1]
                else:
                    vals = vals.squeeze(1)
            elif vals.ndim > 2:
                # Fallback: reduce non-batch dimensions to one scalar per sample.
                reduce_dims = tuple(range(1, vals.ndim))
                vals = vals.mean(dim=reduce_dims)

            batch_scores = [float(x) for x in vals.detach().cpu().tolist()]
            if len(batch_scores) != len(batch_docs):
                if not batch_scores:
                    batch_scores = [0.0] * len(batch_docs)
                elif len(batch_scores) == 1:
                    batch_scores = batch_scores * len(batch_docs)
                else:
                    batch_scores = batch_scores[: len(batch_docs)]
            scores.extend(batch_scores)
        logger.info(
            "Rerank output: model=%s scores=%s min=%s max=%s",
            self.reranker_model_name,
            len(scores),
            min(scores) if scores else None,
            max(scores) if scores else None,
        )
        return scores

    def _rebuild_index(self) -> None:
        if self.dimension is None:
            self.dimension = 1024
        backend = self.vector_backend
        if backend == "zvec" and zvec is None:
            logger.warning("vector_backend=zvec but zvec is unavailable, fallback to faiss/numpy")
            backend = "faiss"
        if backend == "zvec":
            dim = int(self.dimension if self._embeddings.size == 0 else self._embeddings.shape[1])
            self._index = self._build_zvec_index(dim)
            if self._embeddings.size > 0:
                self._index.add(self._embeddings.astype(np.float32, copy=False))
            return
        if self._embeddings.size == 0:
            if faiss is not None:
                cpu_index = faiss.IndexFlatIP(int(self.dimension))
                self._index = self._to_faiss_gpu_index(cpu_index)
            else:
                self._index = _NumpyIndexFlatIP(int(self.dimension))
            return
        if faiss is not None:
            cpu_index = faiss.IndexFlatIP(int(self._embeddings.shape[1]))
            self._index = self._to_faiss_gpu_index(cpu_index)
        else:
            self._index = _NumpyIndexFlatIP(int(self._embeddings.shape[1]))
        self._index.add(self._embeddings.astype(np.float32, copy=False))

    def _build_zvec_index(self, dimension: int) -> Any:
        if zvec is None:
            raise RuntimeError("zvec module is not available")
        # 重建前先关掉旧 Collection，否则目录锁还在
        if isinstance(self._index, _ZvecCollectionIndex):
            try:
                self._index.close()
            except Exception:
                pass
            self._index = None
        # 旧假设：FAISS 同款 API（极少数第三方 shim）
        if hasattr(zvec, "IndexFlatIP"):
            return zvec.IndexFlatIP(int(dimension))
        if hasattr(zvec, "Index"):
            return zvec.Index(dim=int(dimension), metric="ip")
        # 官方 zvec：Collection / create_and_open
        if hasattr(zvec, "create_and_open") and hasattr(zvec, "CollectionSchema"):
            return _ZvecCollectionIndex.create(self.index_path, int(dimension))
        raise RuntimeError("Unsupported zvec API: missing Collection/IndexFlatIP/Index")

    def _save_zvec_index(self, index: Any) -> None:
        if isinstance(index, _ZvecCollectionIndex):
            index.flush()
            return
        if hasattr(zvec, "write_index"):
            zvec.write_index(index, str(self.index_path))
            return
        if hasattr(index, "save"):
            index.save(str(self.index_path))
            return
        raise RuntimeError("Unsupported zvec persistence API")

    def _load_zvec_index(self) -> Any:
        if zvec is None:
            return None
        if hasattr(zvec, "create_and_open") and hasattr(zvec, "CollectionSchema"):
            path = Path(self.index_path)
            if path.is_dir():
                return _ZvecCollectionIndex.open_existing(path, self.dimension)
            return None
        if hasattr(zvec, "read_index"):
            return zvec.read_index(str(self.index_path))
        if hasattr(zvec, "load_index"):
            return zvec.load_index(str(self.index_path))
        if hasattr(zvec, "Index") and hasattr(zvec.Index, "load"):
            return zvec.Index.load(str(self.index_path))
        raise RuntimeError("Unsupported zvec load API")

    def _should_use_faiss_gpu(self) -> bool:
        if faiss is None:
            return False
        if self.device != "cuda":
            return False
        env = str(os.getenv("KB_FAISS_USE_GPU") or "").strip().lower()
        if env in {"0", "false", "no", "off"}:
            return False
        has_gpu_api = all(
            hasattr(faiss, name)
            for name in ("StandardGpuResources", "index_cpu_to_gpu")
        )
        return bool(has_gpu_api)

    def _to_faiss_gpu_index(self, cpu_index: Any) -> Any:
        if faiss is None:
            return cpu_index
        if not self._faiss_use_gpu:
            return cpu_index
        try:
            if self._faiss_gpu_resources is None:
                self._faiss_gpu_resources = faiss.StandardGpuResources()
            gpu_index = faiss.index_cpu_to_gpu(self._faiss_gpu_resources, 0, cpu_index)
            logger.info("FAISS index moved to GPU")
            return gpu_index
        except Exception as exc:
            logger.warning("Failed to move FAISS index to GPU, fallback to CPU: %s", exc)
            self._faiss_use_gpu = False
            self._faiss_gpu_resources = None
            return cpu_index

    def clear(self) -> None:
        """
        清空知识库中的所有文档和分片。
        
        此操作不可恢复。会删除：
        - 所有分片记录
        - 所有向量
        - FAISS 索引
        - 但保留文件系统中的元数据和缓存文件
        
        返回值：
            None
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> kb.add_document("doc1.txt", "content1")
            >>> kb.add_document("doc2.txt", "content2")
            >>> print(f"Before clear: {len(kb.list_documents())} documents")
            >>> kb.clear()
            >>> print(f"After clear: {len(kb.list_documents())} documents")
            # 输出：Before clear: 2 documents
            # 输出：After clear: 0 documents
        """
        if self.dimension is None:
            self.dimension = 1024
        self._chunks = []
        self._embeddings = np.zeros((0, int(self.dimension)), dtype=np.float32)
        self._rebuild_index()
        self._save()

    def remove_document(self, filename: str) -> int:
        """
        从知识库中删除指定文件的所有分片。
        
        会找出所有 filename 匹配的分片并删除，包括：
        - 分片记录
        - 对应的向量
        - 从 FAISS 索引中移除
        
        参数说明：
            filename (str)
                要删除的文档文件名。删除是模糊匹配（包含）。
                示例："document" 将匹配 "document.pdf"、"document_v2.pdf" 等
                
        返回值：
            int
                删除的分片数。返回 0 表示未找到该文档。
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> kb.add_document("manual.pdf", "第 1 章...\\n第 2 章...")
            >>> chunks = kb.list_chunks()
            >>> print(f"Before removal: {chunks['count']} chunks")
            >>> removed = kb.remove_document("manual")
            >>> print(f"Removed {removed} chunks")
            >>> chunks = kb.list_chunks()
            >>> print(f"After removal: {chunks['count']} chunks")
        """
        filename_norm = self._normalize_filename(filename)
        if not filename_norm:
            return 0
        target_key = self._filename_key(filename_norm)

        keep_idx = [i for i, c in enumerate(self._chunks) if self._filename_key(c.filename) != target_key]
        removed = len(self._chunks) - len(keep_idx)
        if removed <= 0:
            return 0

        self._chunks = [self._chunks[i] for i in keep_idx]
        if keep_idx:
            self._embeddings = self._embeddings[keep_idx].astype(np.float32, copy=False)
            self.dimension = int(self._embeddings.shape[1])
        else:
            dim = int(self.dimension or 1024)
            self._embeddings = np.zeros((0, dim), dtype=np.float32)
            self.dimension = dim

        self._rebuild_index()
        self._save()
        return removed

    def list_documents(self) -> List[Dict[str, Any]]:
        """
        列出知识库中的所有文档及其统计信息。
        
        返回每个文档的下列信息：
        - 文件名
        - 分片数: 该文档所有的文本分片数
        - 字符数: 该文档所有分片的总字符数
        
        返回值：
            List[Dict[str, Any]]
            包含字典的列表：
            [
                {
                    "filename": str,      # 文档文件名
                    "chunk_count": int,   # 分片数
                    "char_count": int,    # 总字符数
                },
                ...
            ]
            
        示例用法：
            >>> kb = KnowledgeBase()
            >>> docs = kb.list_documents()
            >>> for doc in docs:
            ...     print(f"{doc['filename']}: {doc['chunk_count']} chunks, {doc['char_count']} chars")
            
        输出示例：
            [
                {"filename": "document.pdf", "chunk_count": 12, "char_count": 5834},
                {"filename": "guide.md", "chunk_count": 5, "char_count": 2341},
            ]
        """
        by_name: Dict[str, Dict[str, Any]] = {}
        for chunk in self._chunks:
            item = by_name.get(chunk.filename)
            if item is None:
                item = {
                    "filename": chunk.filename,
                    "chunk_count": 0,
                    "char_count": 0,
                }
                by_name[chunk.filename] = item
            item["chunk_count"] += 1
            item["char_count"] += len(chunk.text)
        return sorted(by_name.values(), key=lambda x: str(x["filename"]).lower())

    def stats(self) -> Dict[str, Any]:
        """
        获取知识库的统计信息和配置详情。
        
        返回值：
            Dict[str, Any]
            包含以下键值对的字典：
            {
                "persist_dir": str,           # 持久化存储目录路径
                "model_cache_dir": str,       # 模型缓存目录路径
                "document_count": int,        # 知识库中的文档数
                "chunk_count": int,           # 知识库中的总分片数
                "dimension": int,             # 向量维度
                "index_total": int,           # FAISS 索引中的向量总数
                "embedding_model": str,       # 嵌入模型名称
                "reranker_model": str,        # 重排序模型名称
                "chat_model": str,            # 聊天模型名称
                "use_lm_studio_chat": bool,   # 是否使用 LM Studio 进行聊天
            }
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> kb.add_document("test.txt", "sample content")
            >>> stats = kb.stats()
            >>> print(f"文档数: {stats['document_count']}")
            >>> print(f"分片数: {stats['chunk_count']}")
            >>> print(f"向量维度: {stats['dimension']}")
            >>> print(f"模型: {stats['embedding_model']}")
            
        打印完整统计信息：
            >>> import json
            >>> print(json.dumps(stats, indent=2, ensure_ascii=False))
        """
        dim = self.dimension
        if dim is None and self._embeddings.ndim == 2 and self._embeddings.shape[1] > 0:
            dim = int(self._embeddings.shape[1])
        loaded_models = self._collect_loaded_model_stats()
        total_memory = self._aggregate_model_memory(loaded_models)
        process_memory = self._collect_process_memory()
        gpu_memory = self._collect_gpu_memory()
        system_usage = self._collect_system_usage()
        gpu_usage = self._collect_gpu_usage()
        processes = self._collect_process_usage(gpu_usage=gpu_usage)
        return {
            "persist_dir": str(self.persist_dir),
            "model_cache_dir": str(self.model_cache_dir),
            "document_count": len({c.filename for c in self._chunks}),
            "chunk_count": len(self._chunks),
            "dimension": int(dim or 0),
            "index_total": int(self._index.ntotal) if self._index is not None else 0,
            "embedding_model": self.embedding_model_name,
            "reranker_model": self.reranker_model_name,
            "chat_model": self.chat_model_name,
            "use_lm_studio_chat": self.use_lm_studio_chat,
            "loaded_models": loaded_models,
            "models_memory_total": total_memory,
            "process_memory": process_memory,
            "gpu_memory": gpu_memory,
            "system_usage": system_usage,
            "gpu_usage": gpu_usage,
            "processes": processes,
        }

    @staticmethod
    def _human_bytes(num_bytes: int | float | None) -> str | None:
        if num_bytes is None:
            return None
        try:
            val = float(num_bytes)
        except Exception:
            return None
        if val < 0:
            return None
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        while val >= 1024 and idx < len(units) - 1:
            val /= 1024.0
            idx += 1
        return f"{val:.2f} {units[idx]}"

    @classmethod
    def _torch_module_memory(cls, module: Any) -> Dict[str, Any] | None:
        if module is None:
            return None
        by_device: Dict[str, int] = {}
        tensors: List[torch.Tensor] = []
        try:
            tensors.extend(list(module.parameters()))
        except Exception:
            pass
        try:
            tensors.extend(list(module.buffers()))
        except Exception:
            pass
        for tensor in tensors:
            if tensor is None:
                continue
            try:
                numel = tensor.numel()
                elem_size = tensor.element_size()
                bytes_used = int(numel * elem_size)
            except Exception:
                continue
            device = str(getattr(tensor, "device", "cpu"))
            if device.startswith("cuda"):
                device_key = "cuda"
            elif device.startswith("cpu"):
                device_key = "cpu"
            else:
                device_key = device
            by_device[device_key] = by_device.get(device_key, 0) + bytes_used
        total = int(sum(by_device.values()))
        human_by_device = {k: cls._human_bytes(v) for k, v in by_device.items()}
        return {
            "bytes_by_device": by_device,
            "bytes_total": total,
            "human_by_device": human_by_device,
            "human_total": cls._human_bytes(total),
        }

    def _collect_loaded_model_stats(self) -> Dict[str, Any]:
        loaded: Dict[str, Any] = {}

        embed_backend = (
            "lm_studio"
            if self.use_lm_studio_embeddings and self._lm_client is not None
            else "local"
        )
        embed_model_obj = self._embed_model if embed_backend == "local" else None
        loaded["embedding"] = {
            "name": self.embedding_model_name,
            "backend": embed_backend,
            "loaded": bool(embed_model_obj) if embed_backend == "local" else None,
            "device": self.device if embed_backend == "local" else None,
            "memory": self._torch_module_memory(embed_model_obj),
            "note": None if embed_backend == "local" else "remote_backend",
        }

        rerank_backend = (
            "lm_studio"
            if self.use_lm_studio_rerank and self._lm_client is not None
            else "local"
        )
        rerank_model_obj = self._rerank_model if rerank_backend == "local" else None
        loaded["reranker"] = {
            "name": self.reranker_model_name,
            "backend": rerank_backend,
            "loaded": bool(rerank_model_obj) if rerank_backend == "local" else None,
            "device": self.device if rerank_backend == "local" else None,
            "memory": self._torch_module_memory(rerank_model_obj),
            "note": None if rerank_backend == "local" else "remote_backend",
        }

        chat_backend = (
            "lm_studio"
            if self.use_lm_studio_chat and self._lm_client is not None
            else "local"
        )
        chat_model_obj = None
        chat_loaded_name = self.chat_model_name
        if self._chat_backend is not None:
            chat_loaded_name = self._chat_backend._loaded_model_name or chat_loaded_name
            if chat_backend == "local":
                chat_model_obj = getattr(self._chat_backend, "_model", None)
        loaded["chat"] = {
            "name": chat_loaded_name,
            "backend": chat_backend,
            "loaded": bool(chat_model_obj) if chat_backend == "local" else None,
            "device": self.device if chat_backend == "local" else None,
            "memory": self._torch_module_memory(chat_model_obj),
            "note": None if chat_backend == "local" else "remote_backend",
        }

        return loaded

    @classmethod
    def _aggregate_model_memory(cls, loaded_models: Dict[str, Any]) -> Dict[str, Any]:
        total_by_device: Dict[str, int] = {}
        for _, info in (loaded_models or {}).items():
            memory = info.get("memory") if isinstance(info, dict) else None
            if not isinstance(memory, dict):
                continue
            by_device = memory.get("bytes_by_device")
            if not isinstance(by_device, dict):
                continue
            for device, val in by_device.items():
                try:
                    bytes_used = int(val)
                except Exception:
                    continue
                total_by_device[device] = total_by_device.get(device, 0) + bytes_used
        total = int(sum(total_by_device.values()))
        return {
            "bytes_by_device": total_by_device,
            "bytes_total": total,
            "human_by_device": {k: cls._human_bytes(v) for k, v in total_by_device.items()},
            "human_total": cls._human_bytes(total),
        }

    def _touch_model(self, key: str) -> None:
        try:
            self._model_last_used[str(key)] = time.time()
        except Exception:
            return

    def request_started(self) -> None:
        with self._active_lock:
            self._active_requests += 1

    def request_finished(self) -> None:
        with self._active_lock:
            self._active_requests = max(0, self._active_requests - 1)

    def _can_release_gpu(self) -> bool:
        with self._active_lock:
            return self._active_requests <= 0

    def _unload_embed_model(self) -> bool:
        if self._embed_model is None and self._embed_tokenizer is None:
            return False
        self._embed_model = None
        self._embed_tokenizer = None
        return True

    def _unload_rerank_model(self) -> bool:
        if self._rerank_model is None and self._rerank_tokenizer is None:
            return False
        self._rerank_model = None
        self._rerank_tokenizer = None
        return True

    def _unload_chat_model(self) -> bool:
        if self._chat_backend is None:
            return False
        try:
            return bool(self._chat_backend.unload())
        except Exception:
            return False

    def _release_gpu_cache(self) -> None:
        if not torch.cuda.is_available():
            return
        try:
            gc.collect()
        except Exception:
            pass
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass

    def release_idle_gpu(self) -> None:
        # logger.info("[release_idle_gpu] 开始执行: torch.cuda.is_available=%s", torch.cuda.is_available())
        if not torch.cuda.is_available():
            # logger.info("[release_idle_gpu] CUDA 不可用，跳过释放")
            return
        can_release = self._can_release_gpu()
        # logger.info("[release_idle_gpu] _can_release_gpu=%s", can_release)
        if not can_release:
            logger.info("[release_idle_gpu] 不满足释放条件，跳过")
            return
        if self.release_gpu_cache:
            logger.info("[release_idle_gpu] 配置要求每次都清理 GPU cache，执行 _release_gpu_cache()")
            self._release_gpu_cache()
        idle_seconds = int(self.unload_models_idle_seconds or 0)
        logger.info("[release_idle_gpu] 配置 idle_seconds=%s", idle_seconds)
        if idle_seconds <= 0:
            logger.info("[release_idle_gpu] idle_seconds<=0，跳过模型卸载")
            return
        now = time.time()
        unloaded_models = []
        # 嵌入模型判断
        last_embed = self._model_last_used.get("embedding")
        logger.info("[release_idle_gpu] embedding: loaded=%s, use_lm_studio=%s, last_used=%s, now=%s, idle=%s", self._embed_model is not None, self.use_lm_studio_embeddings, last_embed, now, (now - last_embed) if last_embed else None)
        if (
            self._embed_model is not None
            and not self.use_lm_studio_embeddings
            and last_embed is not None
            and (now - last_embed) >= idle_seconds
        ):
            logger.info("[release_idle_gpu] 满足 embedding 卸载条件，执行 _unload_embed_model()")
            if self._unload_embed_model():
                unloaded_models.append("embedding")
        # reranker 模型判断
        last_rerank = self._model_last_used.get("reranker")
        logger.info("[release_idle_gpu] reranker: loaded=%s, use_lm_studio=%s, last_used=%s, now=%s, idle=%s", self._rerank_model is not None, self.use_lm_studio_rerank, last_rerank, now, (now - last_rerank) if last_rerank else None)
        if (
            self._rerank_model is not None
            and not self.use_lm_studio_rerank
            and last_rerank is not None
            and (now - last_rerank) >= idle_seconds
        ):
            logger.info("[release_idle_gpu] 满足 reranker 卸载条件，执行 _unload_rerank_model()")
            if self._unload_rerank_model():
                unloaded_models.append("reranker")
        # chat 模型判断
        last_chat = self._model_last_used.get("chat")
        logger.info("[release_idle_gpu] chat: loaded=%s, use_lm_studio=%s, last_used=%s, now=%s, idle=%s", hasattr(self, '_chat_backend') and getattr(self._chat_backend, 'model', None) is not None, self.use_lm_studio_chat, last_chat, now, (now - last_chat) if last_chat else None)
        if (
            not self.use_lm_studio_chat
            and last_chat is not None
            and (now - last_chat) >= idle_seconds
        ):
            logger.info("[release_idle_gpu] 满足 chat 卸载条件，执行 _unload_chat_model()")
            if self._unload_chat_model():
                unloaded_models.append("chat")
        if unloaded_models:
            logger.info("[release_idle_gpu] 已清理模型: %s，执行 _release_gpu_cache()", ', '.join(unloaded_models))
            self._release_gpu_cache()
            logger.info(f"release_idle_gpu: 已清理模型: {', '.join(unloaded_models)}")
        else:
            logger.info("release_idle_gpu: 没有模型需要清理")

    @classmethod
    def _collect_process_memory(cls) -> Dict[str, Any] | None:
        try:
            import psutil  # type: ignore
        except Exception:
            psutil = None

        if psutil is not None:
            try:
                proc = psutil.Process(os.getpid())
                info = proc.memory_info()
                full = None
                try:
                    full = proc.memory_full_info()
                except Exception:
                    full = None
                return {
                    "rss_bytes": int(getattr(info, "rss", 0)),
                    "vms_bytes": int(getattr(info, "vms", 0)),
                    "shared_bytes": int(getattr(info, "shared", 0)),
                    "text_bytes": int(getattr(info, "text", 0)),
                    "data_bytes": int(getattr(info, "data", 0)),
                    "dirty_bytes": int(getattr(info, "dirty", 0)),
                    "uss_bytes": int(getattr(full, "uss", 0)) if full is not None else None,
                    "pss_bytes": int(getattr(full, "pss", 0)) if full is not None else None,
                    "human_rss": cls._human_bytes(getattr(info, "rss", None)),
                    "human_vms": cls._human_bytes(getattr(info, "vms", None)),
                }
            except Exception:
                return None

        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                        ("PrivateUsage", ctypes.c_size_t),
                    ]

                counters = PROCESS_MEMORY_COUNTERS_EX()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
                GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
                GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
                handle = GetCurrentProcess()
                if not GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return None

                return {
                    "working_set_bytes": int(counters.WorkingSetSize),
                    "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
                    "pagefile_bytes": int(counters.PagefileUsage),
                    "peak_pagefile_bytes": int(counters.PeakPagefileUsage),
                    "private_bytes": int(counters.PrivateUsage),
                    "human_working_set": cls._human_bytes(counters.WorkingSetSize),
                    "human_private": cls._human_bytes(counters.PrivateUsage),
                }
            except Exception:
                return None

        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss_kb = getattr(usage, "ru_maxrss", 0)
            rss_bytes = int(rss_kb) * 1024
            return {
                "max_rss_bytes": rss_bytes,
                "human_max_rss": cls._human_bytes(rss_bytes),
                "note": "ru_maxrss_only",
            }
        except Exception:
            return None

    @staticmethod
    def _collect_gpu_memory() -> Dict[str, Any] | None:
        if not torch.cuda.is_available():
            return None
        devices: List[Dict[str, Any]] = []
        try:
            count = torch.cuda.device_count()
        except Exception:
            count = 0
        for idx in range(count):
            try:
                props = torch.cuda.get_device_properties(idx)
                free_bytes, total_bytes = torch.cuda.mem_get_info(idx)
                allocated = torch.cuda.memory_allocated(idx)
                reserved = torch.cuda.memory_reserved(idx)
                max_alloc = torch.cuda.max_memory_allocated(idx)
                max_reserved = torch.cuda.max_memory_reserved(idx)
            except Exception:
                continue
            devices.append(
                {
                    "index": idx,
                    "name": getattr(props, "name", None),
                    "total_bytes": int(total_bytes),
                    "free_bytes": int(free_bytes),
                    "allocated_bytes": int(allocated),
                    "reserved_bytes": int(reserved),
                    "max_allocated_bytes": int(max_alloc),
                    "max_reserved_bytes": int(max_reserved),
                    "human_total": KnowledgeBase._human_bytes(total_bytes),
                    "human_free": KnowledgeBase._human_bytes(free_bytes),
                    "human_allocated": KnowledgeBase._human_bytes(allocated),
                    "human_reserved": KnowledgeBase._human_bytes(reserved),
                }
            )
        return {"device_count": len(devices), "devices": devices}

    @classmethod
    def _collect_system_usage(cls) -> Dict[str, Any] | None:
        try:
            import psutil  # type: ignore
        except Exception:
            return None

        try:
            cpu_percent = float(psutil.cpu_percent(interval=0.1))
        except Exception:
            cpu_percent = None

        try:
            cpu_count = int(psutil.cpu_count(logical=True) or 0)
        except Exception:
            cpu_count = None

        vm = None
        try:
            vm = psutil.virtual_memory()
        except Exception:
            vm = None

        swap = None
        try:
            swap = psutil.swap_memory()
        except Exception:
            swap = None

        load_avg = None
        try:
            load_avg = os.getloadavg()
        except Exception:
            load_avg = None

        result: Dict[str, Any] = {
            "cpu_percent": cpu_percent,
            "cpu_count": cpu_count,
            "load_avg": load_avg,
        }
        if vm is not None:
            result["memory"] = {
                "total_bytes": int(getattr(vm, "total", 0)),
                "available_bytes": int(getattr(vm, "available", 0)),
                "used_bytes": int(getattr(vm, "used", 0)),
                "free_bytes": int(getattr(vm, "free", 0)),
                "percent": float(getattr(vm, "percent", 0.0)),
                "human_total": cls._human_bytes(getattr(vm, "total", None)),
                "human_used": cls._human_bytes(getattr(vm, "used", None)),
                "human_available": cls._human_bytes(getattr(vm, "available", None)),
            }
        if swap is not None:
            result["swap"] = {
                "total_bytes": int(getattr(swap, "total", 0)),
                "used_bytes": int(getattr(swap, "used", 0)),
                "free_bytes": int(getattr(swap, "free", 0)),
                "percent": float(getattr(swap, "percent", 0.0)),
                "human_total": cls._human_bytes(getattr(swap, "total", None)),
                "human_used": cls._human_bytes(getattr(swap, "used", None)),
            }
        return result

    @classmethod
    def _collect_gpu_usage(cls) -> Dict[str, Any] | None:
        try:
            import pynvml  # type: ignore
        except Exception:
            return None

        try:
            pynvml.nvmlInit()
        except Exception:
            return None

        devices: List[Dict[str, Any]] = []
        total_gpu_mem = 0
        try:
            count = int(pynvml.nvmlDeviceGetCount())
        except Exception:
            count = 0

        for idx in range(count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="ignore")
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                total_gpu_mem += int(getattr(mem, "total", 0))
                util_map: Dict[int, Dict[str, float]] = {}
                if hasattr(pynvml, "nvmlDeviceGetProcessUtilization"):
                    try:
                        samples = pynvml.nvmlDeviceGetProcessUtilization(handle, 0)
                    except Exception:
                        samples = []
                    for sample in samples or []:
                        try:
                            pid = int(getattr(sample, "pid", 0))
                        except Exception:
                            continue
                        if pid <= 0:
                            continue
                        try:
                            sm_util = float(getattr(sample, "smUtil", 0.0))
                        except Exception:
                            sm_util = 0.0
                        try:
                            mem_util = float(getattr(sample, "memUtil", 0.0))
                        except Exception:
                            mem_util = 0.0
                        util_map[pid] = {
                            "gpu_util_percent": sm_util,
                            "mem_util_percent": mem_util,
                        }

                procs = []
                try:
                    proc_infos = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                except Exception:
                    proc_infos = []
                for p in proc_infos or []:
                    try:
                        used = int(getattr(p, "usedGpuMemory", 0))
                    except Exception:
                        used = 0
                    pid = int(getattr(p, "pid", 0))
                    util = util_map.get(pid, {})
                    procs.append(
                        {
                            "pid": pid,
                            "used_memory_bytes": used,
                            "human_used_memory": cls._human_bytes(used),
                            "gpu_util_percent": util.get("gpu_util_percent"),
                            "gpu_mem_util_percent": util.get("mem_util_percent"),
                        }
                    )
                devices.append(
                    {
                        "index": idx,
                        "name": name,
                        "utilization_gpu_percent": float(getattr(util, "gpu", 0.0)),
                        "utilization_memory_percent": float(getattr(util, "memory", 0.0)),
                        "memory_total_bytes": int(getattr(mem, "total", 0)),
                        "memory_used_bytes": int(getattr(mem, "used", 0)),
                        "memory_free_bytes": int(getattr(mem, "free", 0)),
                        "human_memory_total": cls._human_bytes(getattr(mem, "total", None)),
                        "human_memory_used": cls._human_bytes(getattr(mem, "used", None)),
                        "human_memory_free": cls._human_bytes(getattr(mem, "free", None)),
                        "processes": procs,
                        "process_utilization_available": bool(util_map),
                    }
                )
            except Exception:
                continue

        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass

        return {
            "device_count": len(devices),
            "devices": devices,
            "total_memory_bytes": total_gpu_mem,
            "human_total_memory": cls._human_bytes(total_gpu_mem),
        }

    @classmethod
    def _collect_process_usage(cls, gpu_usage: Dict[str, Any] | None = None) -> List[Dict[str, Any]] | None:
        try:
            import psutil  # type: ignore
        except Exception:
            return None

        allowed_pids: set[int] | None = None
        try:
            current = psutil.Process(os.getpid())
            allowed_pids = {int(current.pid)}
            try:
                for child in current.children(recursive=True):
                    try:
                        allowed_pids.add(int(child.pid))
                    except Exception:
                        continue
            except Exception:
                pass
        except Exception:
            allowed_pids = None

        gpu_proc_map: Dict[int, int] = {}
        gpu_util_map: Dict[int, float] = {}
        gpu_mem_util_map: Dict[int, float] = {}
        gpu_total = 0
        if gpu_usage and isinstance(gpu_usage.get("devices"), list):
            for dev in gpu_usage["devices"]:
                try:
                    gpu_total += int(dev.get("memory_total_bytes") or 0)
                except Exception:
                    pass
                for proc in dev.get("processes", []) or []:
                    try:
                        pid = int(proc.get("pid"))
                        used = int(proc.get("used_memory_bytes") or 0)
                    except Exception:
                        continue
                    gpu_proc_map[pid] = gpu_proc_map.get(pid, 0) + used
                    try:
                        util = float(proc.get("gpu_util_percent")) if proc.get("gpu_util_percent") is not None else None
                    except Exception:
                        util = None
                    if util is not None:
                        gpu_util_map[pid] = max(util, gpu_util_map.get(pid, 0.0))
                    try:
                        mem_util = float(proc.get("gpu_mem_util_percent")) if proc.get("gpu_mem_util_percent") is not None else None
                    except Exception:
                        mem_util = None
                    if mem_util is not None:
                        gpu_mem_util_map[pid] = max(mem_util, gpu_mem_util_map.get(pid, 0.0))

        processes: List[Dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "username", "status"]):
            try:
                pid = proc.info.get("pid")
                if allowed_pids is not None and (pid is None or int(pid) not in allowed_pids):
                    continue
                name = proc.info.get("name")
                username = proc.info.get("username")
                status = proc.info.get("status")
                cpu_percent = proc.cpu_percent(interval=None)
                mem_percent = proc.memory_percent()
                mem_info = proc.memory_info()
                rss = int(getattr(mem_info, "rss", 0))
                vms = int(getattr(mem_info, "vms", 0))
            except Exception:
                continue

            gpu_used = gpu_proc_map.get(int(pid), 0) if pid is not None else 0
            gpu_percent = None
            if gpu_total > 0 and gpu_used > 0:
                gpu_percent = round(gpu_used / gpu_total * 100.0, 4)

            processes.append(
                {
                    "pid": int(pid) if pid is not None else None,
                    "name": name,
                    "username": username,
                    "status": status,
                    "cpu_percent": float(cpu_percent) if cpu_percent is not None else None,
                    "memory_percent": float(mem_percent) if mem_percent is not None else None,
                    "memory_rss_bytes": rss,
                    "memory_vms_bytes": vms,
                    "human_memory_rss": cls._human_bytes(rss),
                    "human_memory_vms": cls._human_bytes(vms),
                    "gpu_memory_bytes": gpu_used,
                    "human_gpu_memory": cls._human_bytes(gpu_used),
                    "gpu_memory_percent": gpu_percent,
                    "gpu_util_percent": gpu_util_map.get(int(pid)) if pid is not None else None,
                    "gpu_mem_util_percent": gpu_mem_util_map.get(int(pid)) if pid is not None else None,
                }
            )

        processes.sort(
            key=lambda p: (
                -(p.get("cpu_percent") or 0.0),
                -(p.get("memory_rss_bytes") or 0),
            )
        )
        return processes[:50]

    def warmup_models(
        self, load_embedding: bool = True, load_reranker: bool = True
    ) -> Dict[str, Any]:
        logger.debug("开始预热模型: load_embedding=%s, load_reranker=%s", load_embedding, load_reranker)
        status: Dict[str, Any] = {"embedding_loaded": False, "reranker_loaded": False}

        if load_embedding:
            logger.debug("预热 Embedding 模型...")
            try:
                if self.use_lm_studio_embeddings and self._lm_client is not None:
                    logger.debug("使用 LM Studio Embedding: %s", self.embedding_model_name)
                    self._lm_client.embed_texts(["warmup"], model=self.embedding_model_name)
                else:
                    logger.debug("使用本地 Embedding 模型")
                    self._ensure_embed_model()
                status["embedding_loaded"] = True
                logger.debug("Embedding 模型预热成功")
            except Exception as exc:
                status["embedding_error"] = str(exc)
                logger.exception("Embedding warmup failed")
                logger.debug("Embedding 预热失败: %s", exc)

        if load_reranker:
            logger.debug("预热 Reranker 模型...")
            try:
                if self.use_lm_studio_rerank and self._lm_client is not None:
                    logger.debug("使用 LM Studio Reranker: %s", self.reranker_model_name)
                    self._lm_client.rerank_scores(
                        "warmup",
                        ["warmup"],
                        model=self.reranker_model_name,
                    )
                else:
                    logger.debug("使用本地 Reranker 模型")
                    self._ensure_reranker_model()
                status["reranker_loaded"] = True
                logger.debug("Reranker 模型预热成功")
            except Exception as exc:
                status["reranker_error"] = str(exc)
                logger.exception("Reranker warmup failed")
                logger.debug("Reranker 预热失败: %s", exc)

        logger.info("Warmup result: %s", status)
        logger.debug("模型预热完成")
        return status

    def _split_text(self, text: str) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        # 商业版：语义递归分片；社区或商业包缺失时回退固定长度
        if self._semantic_chunking_allowed():
            try:
                from .commercial.business.chunking import split_semantic
            except ImportError:
                try:
                    from commercial.business.chunking import split_semantic  # type: ignore
                except ImportError:
                    split_semantic = None  # type: ignore
            if split_semantic is not None:
                try:
                    parts = split_semantic(
                        text,
                        chunk_size=self.chunk_size,
                        chunk_overlap=self.chunk_overlap,
                    )
                    if parts:
                        logger.debug(
                            "使用商业语义分片: chunks=%d size=%d overlap=%d",
                            len(parts),
                            self.chunk_size,
                            self.chunk_overlap,
                        )
                        return parts
                except PermissionError:
                    logger.info("语义分片门控拒绝，回退固定长度分片")
                except Exception as exc:
                    logger.warning("语义分片失败，回退固定长度: %s", exc)

        return self._split_text_fixed(text)

    @staticmethod
    def _semantic_chunking_allowed() -> bool:
        try:
            from .commercial.edition import semantic_chunking_allowed
        except ImportError:
            try:
                from commercial.edition import semantic_chunking_allowed  # type: ignore
            except ImportError:
                try:
                    from src.commercial.edition import semantic_chunking_allowed  # type: ignore
                except ImportError:
                    return False
        return bool(semantic_chunking_allowed())

    def _split_text_fixed(self, text: str) -> List[str]:
        """社区默认：固定长度 + 段落/句子软边界。"""
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
        if len(paragraphs) <= 1:
            lines = [l.strip() for l in normalized.split("\n") if l.strip()]
            if len(lines) > 1:
                paragraphs = lines

        segments: List[str] = []
        for para in paragraphs:
            if len(para) <= self.chunk_size:
                segments.append(para)
                continue
            sentences = self._split_sentences(para)
            if not sentences:
                segments.extend(self._split_by_length(para))
                continue
            for sent in sentences:
                if len(sent) <= self.chunk_size:
                    segments.append(sent)
                else:
                    segments.extend(self._split_by_length(sent))

        chunks: List[str] = []
        current = ""
        for seg in segments:
            if not seg:
                continue
            if not current:
                current = seg
                continue
            if len(current) + 1 + len(seg) <= self.chunk_size:
                current = f"{current}\n{seg}"
                continue
            chunks.append(current.strip())
            overlap_text = ""
            if self.chunk_overlap > 0:
                overlap_text = current[-self.chunk_overlap :]
                overlap_text = self._trim_overlap_to_boundary(overlap_text)
            current = f"{overlap_text}\n{seg}".strip() if overlap_text else seg

        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _split_by_length(self, text: str) -> List[str]:
        if not text:
            return []
        size = max(1, int(self.chunk_size))
        parts = []
        start = 0
        while start < len(text):
            part = text[start : start + size].strip()
            if part:
                parts.append(part)
            start += size
        return parts

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        if not text:
            return []
        splitter = re.compile(r"([。！？!?；;])")
        pieces = splitter.split(text)
        sentences: List[str] = []
        i = 0
        while i < len(pieces):
            chunk = pieces[i]
            if i + 1 < len(pieces):
                chunk = f"{chunk}{pieces[i + 1]}"
                i += 2
            else:
                i += 1
            cleaned = chunk.strip()
            if cleaned:
                sentences.append(cleaned)
        return sentences

    @staticmethod
    def _trim_overlap_to_boundary(text: str) -> str:
        if not text:
            return ""
        # Prefer keeping overlap starting from last sentence boundary.
        match = re.search(r"[。！？!?；;](?!.*[。！？!?；;])", text)
        if match:
            return text[match.end() :].strip()
        return text.strip()

    @staticmethod
    def _read_text(path: Path) -> str:
        return BaseDocumentParser.read_text(path)

    @staticmethod
    def _extract_text_from_xml_bytes(data: bytes) -> str:
        return BaseDocumentParser.extract_text_from_xml_bytes(data)

    def _read_pdf(self, path: Path) -> str:
        return self._document_parser.read_pdf(path)

    def _read_docx(self, path: Path) -> str:
        return self._document_parser.read_docx(path)

    def _read_doc(self, path: Path) -> str:
        return self._document_parser.read_doc(path)

    def _read_excel(self, path: Path) -> str:
        return self._document_parser.read_excel(path)

    def _read_ofd(self, path: Path) -> str:
        return self._document_parser.read_ofd(path)

    def _read_pws(self, path: Path) -> str:
        return self._document_parser.read_pws(path)

    @staticmethod
    def _read_binary_strings(path: Path) -> str:
        return BaseDocumentParser.read_binary_strings(path)

    def _extract_text(self, path: Path) -> str:
        return self._document_parser.extract_text(path)

    def add_document(self, filename: str, text: str) -> int:
        """
        添加文本文档到知识库。
        
        系统会自动将文本分块、生成向量、建立索引并保存。
        如果同名文档已存在，会先删除旧版本，再添加新版本。
        
        参数说明：
            filename (str)
                文档文件名。用于标识和分组相关的文本块。
                相同 filename 的多个添加会互相替换，不会重复。
                示例："document.txt"、"README.md"
                
            text (str)
                文档内容文本。支持任意长度的文本。
                自动处理空白字符、编码等问题。
                
        返回值：
            int
                本次添加成功分块的数量。
                返回 0 表示文本为空或处理失败。
        
        异常处理：
            ValueError
                如果 filename 为空或无效会抛出异常。
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> chunks = kb.add_document("guide.md", "# Python 快速开始\\n...")
            >>> print(f"Created {chunks} chunks")
            
        内部流程：
            1. 规范化文件名
            2. 检查并删除同名旧文档的所有分块
            3. 将文本按 chunk_size 和 chunk_overlap 分块
            4. 为每个分块生成向量（embedding）
            5. 更新向量索引
            6. 保存到磁盘
        """
        logger.debug("开始添加文档: filename='%s', text_length=%d", filename, len(text) if text else 0)
        
        filename_norm = self._normalize_filename(filename)
        if not filename_norm:
            logger.error("文件名为空或无效")
            raise ValueError("filename is required")
        logger.debug("规范化文件名: '%s' -> '%s'", filename, filename_norm)
        
        text = (text or "").strip()
        if not text:
            logger.debug("文本为空，跳过添加")
            return 0

        target_key = self._filename_key(filename_norm)
        keep_idx = [i for i, c in enumerate(self._chunks) if self._filename_key(c.filename) != target_key]
        removed_count = len(self._chunks) - len(keep_idx)
        if removed_count > 0:
            logger.debug("删除旧文档的 %d 个分块", removed_count)
            self._chunks = [self._chunks[i] for i in keep_idx]
            self._embeddings = self._embeddings[keep_idx]

        logger.debug("开始文本分块...")
        parts = self._split_text(text)
        if not parts:
            logger.debug("分块结果为空")
            self._rebuild_index()
            self._save()
            return 0
        logger.debug("文本分块完成，得到 %d 个分块", len(parts))

        logger.debug("开始生成向量嵌入...")
        vecs = self._embed_texts(parts)
        if vecs.shape[0] != len(parts):
            logger.error("向量数量与分块数量不匹配: %d vs %d", vecs.shape[0], len(parts))
            raise RuntimeError("Embedding count mismatch while adding document")
        logger.debug("向量生成完成，shape=%s", vecs.shape)

        new_chunks = [_Chunk(filename=filename_norm, text=part) for part in parts]
        if self._embeddings.size == 0:
            logger.debug("这是第一个文档，初始化嵌入矩阵")
            self._embeddings = vecs
        else:
            logger.debug("合并新向量到现有嵌入矩阵")
            self._embeddings = np.vstack([self._embeddings, vecs]).astype(
                np.float32, copy=False
            )
        self._chunks.extend(new_chunks)
        logger.debug("总分块数: %d, 总向量数: %d", len(self._chunks), self._embeddings.shape[0])

        self.dimension = int(self._embeddings.shape[1])
        logger.debug("重建向量索引...")
        self._rebuild_index()
        logger.debug("保存到磁盘...")
        self._save()
        logger.info("文档添加完成: filename='%s', chunks=%d", filename_norm, len(new_chunks))
        return len(new_chunks)

    def add_text_file(self, file_path: str) -> int:
        """
        从文件系统中读取文本文件并添加到知识库。
        
        支持的文件格式：PDF、Word、Markdown、纯文本等。
        系统会自动识别文件格式并提取文本内容。
        
        参数说明：
            file_path (str)
                文件的本地路径。可为相对路径或绝对路径。
                示例："./documents/manual.pdf"、"C:\\docs\\guide.docx"
                
        返回值：
            int
                成功分块的数量。返回 0 表示文件不存在或为空。
        
        异常处理：
            FileNotFoundError: 文件不存在
            ValueError: 文件不可读或格式不支持
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> chunks = kb.add_text_file("./local_file.pdf")
            >>> print(f"Added {chunks} chunks from PDF")
            
        支持的文件类型：
            - .txt: 纯文本文件
            - .pdf: PDF 文档
            - .docx: Microsoft Word 文档
            - .md / .rst: Markdown/ReStructuredText
            - .json / .csv: 数据文件
            - .py / .yaml: 代码和配置文件
        """
        path = Path(file_path)
        text = self._extract_text(path)
        return self.add_document(self._normalize_filename(path.name), text)

    @staticmethod
    def _decode_uploaded_text_bytes(data: bytes, encoding: str | None = None) -> str:
        return BaseDocumentParser.decode_uploaded_text_bytes(data, encoding=encoding)

    def add_uploaded_file(
        self, filename: str, content: bytes, encoding: str | None = None
    ) -> int:
        """
        添加上传的文件内容（二进制数据）到知识库。
        
        常用于处理 Web 应用中的文件上传。根据文件扩展名自动识别
        文件格式并相应地处理（文本解码或二进制提取）。
        
        参数说明：
            filename (str)
                上传文件的原始文件名。用于确定文件类型和在知识库中的身份。
                示例："report.pdf"、"document.docx"
                
            content (bytes)
                文件的二进制内容。从上传请求直接获取的原始字节。
                
            encoding (str, 可选)
                文本文件的字符编码。如果指定，优先使用该编码解码。
                默认值：None（自动检测：utf-8-sig > utf-8 > gb18030 > ...）
                示例："utf-8"、"gb2312"、"utf-16"
                
        返回值：
            int
                成功分块的数量。返回 0 表示文件为空或处理失败。
        
        异常处理：
            ValueError
                - filename 为空或无效
                - 指定的 encoding 无法解码文件
        
        示例用法：
            >>> from pathlib import Path
            >>> with open("document.pdf", "rb") as f:
            ...     content = f.read()
            >>> kb = KnowledgeBase()
            >>> chunks = kb.add_uploaded_file("document.pdf", content)
            
        文件处理流程：
            1. 检查文件扩展名
            2. 对于文本文件(.txt, .md, .json等)：直接用指定或自动检测的编码解码
            3. 对于二进制文件(.pdf, .docx)：
               - 尝试用二进制提取器提取文本
               - 失败时降级为文本解码处理
            4. 调用 add_document() 添加到知识库
        """
        filename_clean = self._normalize_filename(filename)
        if not filename_clean:
            raise ValueError("filename is required")
        data = bytes(content or b"")
        if not data:
            return 0

        upload_tmp_dir = self.persist_dir / ".upload_tmp"
        upload_tmp_dir.mkdir(parents=True, exist_ok=True)
        text = self._document_parser.extract_uploaded_file_text(
            filename=filename_clean,
            content=data,
            encoding=encoding,
            temp_dir=upload_tmp_dir,
        )
        return self.add_document(filename_clean, text)

    def list_chunks(
        self,
        page_index: int = 1,
        page_size: int = 20,
        filename: str | None = None,
        query: str | None = None,
    ) -> Dict[str, Any]:
        """
        列出知识库中的文本分片，支持分页、筛选和搜索。
        
        可按文件名筛选或按关键词搜索分片内容，返回分页结果。
        
        参数说明：
            page_index (int, 可选)
                页码（从 1 开始）。默认值：1
                示例：page_index=2 获取第 2 页
                
            page_size (int, 可选)
                每页数量。默认值：20
                示例：page_size=50 每页显示 50 个分片
                范围：[1, ∞)
                
            filename (str, 可选)
                按源文档文件名筛选。None 表示不筛选，列出所有分片。
                筛选是模糊匹配（包含）。
                示例：filename="document" 将匹配 "document.pdf"、"document_v2.pdf" 等
                默认值：None（不筛选）
                
            query (str, 可选)
                按分片内容关键词搜索（不使用向量，普通文本搜索）。
                搜索是不区分大小写的包含匹配。
                示例：query="python" 将匹配包含 "python" 或 "Python" 的分片
                默认值：None（不搜索）
                
        返回值：
            Dict[str, Any]
            包含以下键值对的字典：
            {
                "count": int,                    # 满足条件的总分片数
                "page_index": int,               # 当前页码
                "page_size": int,                # 每页数量
                "total_pages": int,              # 总页数
                "chunks": [                      # 当前页的分片列表
                    {
                        "id": str,               # 分片唯一标识
                        "filename": str,         # 源文档文件名
                        "text": str,             # 分片文本内容
                    },
                    ...
                ]
            }
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> # 获取第一页（20个分片）
            >>> result = kb.list_chunks(page_index=1, page_size=20)
            >>> print(f"Total chunks: {result['count']}")
            
            >>> # 列出某个文件的所有分片
            >>> result = kb.list_chunks(filename="document", page_size=100)
            
            >>> # 搜索包含特定内容的分片
            >>> result = kb.list_chunks(query="python", page_size=10)
            
            >>> # 组合：列出 document.pdf 中包含 "api" 的分片
            >>> result = kb.list_chunks(
            ...     filename="document",
            ...     query="api",
            ...     page_index=1,
            ...     page_size=20
            ... )
        
        搜索行为：
            - page_index, page_size: 用于分页计算
            - filename: 在所有分片中筛选出 filename 键包含该值的分片（包含匹配）
            - query: 在已筛选的分片中继续按 text 内容搜索（包含匹配，不区分大小写）
            - 两个筛选条件是 AND 关系
        """
        page_index = max(1, int(page_index))
        page_size = max(1, int(page_size))
        filename_key = self._filename_key(filename) if filename else None
        query_norm = (query or "").strip().lower()

        items: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(self._chunks):
            if filename_key and self._filename_key(chunk.filename) != filename_key:
                continue
            if query_norm and query_norm not in (chunk.text or "").lower():
                continue
            items.append(
                {
                    "id": int(idx),
                    "filename": chunk.filename,
                    "text": chunk.text,
                    "char_count": len(chunk.text or ""),
                }
            )

        total = len(items)
        start = (page_index - 1) * page_size
        end = start + page_size
        return {"total": total, "items": items[start:end]}

    def update_chunk(self, chunk_id: int, text: str) -> None:
        """
        更新指定 ID 的分片的文本内容。
        
        详细操作：
        1. 根据 chunk_id 查找对应的分片
        2. 更新其文本内容
        3. 重新为新文本生成向量
        4. 编不写向量索引
        5. 保存所有改动到磁盘
        
        参数说明：
            chunk_id (int)
                要更新的分片的序号 ID。表示分片在整个知识库中的位置（造时 0 开始）。
                示例：chunk_id=5 表示第 6 个分片
                
            text (str)
                新的分片文本内容。将覆盖原分片的整个内容。
                
        异常处理：
            IndexError: chunk_id 超出范围（分片不存在）
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> kb.add_document("test.txt", "original content")
            >>> chunks = kb.list_chunks()
            >>> chunk_id = 0
            >>> kb.update_chunk(chunk_id, "updated content")
            >>> # now kb.search("updated") will return this chunk
        """
        idx = int(chunk_id)
        if idx < 0 or idx >= len(self._chunks):
            raise IndexError("chunk_id out of range")
        new_text = (text or "").strip()
        if not new_text:
            raise ValueError("text is required")
        vecs = self._embed_texts([new_text])
        if vecs.shape[0] != 1:
            raise RuntimeError("Embedding count mismatch while updating chunk")
        self._chunks[idx].text = new_text
        if self._embeddings.size == 0:
            self._embeddings = vecs
        else:
            self._embeddings[idx] = vecs[0]
        self._rebuild_index()
        self._save()

    def delete_chunk(self, chunk_id: int) -> None:
        """
        删除指定 ID 的分片。
        
        该方法会从知识库中永久移除一个文本分片，包括其对应的向量数据和索引。
        此操作会自动更新 FAISS 索引和向量数组。
        
        详细操作流程：
        1. 验证 chunk_id 范围（必须在 [0, chunk_count) 内）
        2. 从分片列表中移除对应分片
        3. 从向量矩阵中删除对应的行（删除其向量表示）
        4. 重新构建 FAISS 索引（或 NumPy 备选索引）
        5. 保存改动到磁盘
        
        参数说明：
            chunk_id (int)
                要删除的分片的 ID。是该分片在整个知识库中的位置索引（从 0 开始）。
                示例：
                - chunk_id=0 删除第 1 个分片
                - chunk_id=5 删除第 6 个分片
                
        异常处理：
            IndexError
                当 chunk_id < 0 或 chunk_id >= 知识库中的总分片数时抛出
                示例错误信息：\"chunk_id out of range\"
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> kb.add_document("test.txt", "content1\\ncontent2\\ncontent3")
            >>> chunks = kb.list_chunks(page_size=100)
            >>> print(f"删除前: {chunks['count']} 个分片")
            >>> # 删除第 2 个分片 (ID=1)
            >>> kb.delete_chunk(1)
            >>> chunks = kb.list_chunks(page_size=100)
            >>> print(f"删除后: {chunks['count']} 个分片")
            删除前: 3 个分片
            删除后: 2 个分片
        
        性能特性：
            - 时间复杂度：O(n)，其中 n 为知识库中的分片数（需要重建索引）
            - 空间复杂度：O(n)，需要在内存中处理所有向量
            - 建议：删除大量分片时考虑使用 remove_document() 批量删除
        """
        idx = int(chunk_id)
        if idx < 0 or idx >= len(self._chunks):
            raise IndexError("chunk_id out of range")
        self._chunks.pop(idx)
        if self._embeddings.size > 0:
            self._embeddings = np.delete(self._embeddings, idx, axis=0)
        else:
            dim = int(self.dimension or 1024)
            self._embeddings = np.zeros((0, dim), dtype=np.float32)
        self._rebuild_index()
        self._save()

    def rebuild_chunks_for_filename(self, filename: str) -> int:
        """
        重新构建指定文件的所有分片。
        
        需要先前参祖先明了该文件已经存在于知识库中。
        此方法与直接称改 add_document() 等效，需要旧城了文档内容和旧的分片。
        
        详细操作：
        1. 验证 filename 已存在于知识库中
        2. 丢弃该文件的所有旧分片
        3. 丢弃对应的旧向量
        4. 重新下载文件内容或调用外部应用提供文本
        5. 按新 chunk_size 和 chunk_overlap 分块
        6. 生成新向量和索引
        7. 保存
        
        参数说明：
            filename (str)
                要重构的文档文件名（必须具存于知识库）。
                示例："document.pdf"
                
        返回值：
            int
                重构后新的分片数。返回 0 表示失败或文档不存在。
        
        异常处理：
            ValueError: 指定文件不存在（不是一个已上载文档）
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> kb.add_document("article.md", "original markdown content...")
            >>> # 一段时间后，修改了 chunk_size
            >>> kb.chunk_size = 500  # 改为 500
            >>> # 重新构建文档的分片
            >>> new_chunks = kb.rebuild_chunks_for_filename("article.md")
            >>> print(f"Rebuilt with {new_chunks} chunks (new chunk_size=500)")
        """
        filename_norm = self._normalize_filename(filename)
        if not filename_norm:
            raise ValueError("filename is required")

        target_key = self._filename_key(filename_norm)
        texts = [c.text for c in self._chunks if self._filename_key(c.filename) == target_key]
        if not texts:
            raise FileNotFoundError(f"No chunks found for filename: {filename_norm}")

        keep_idx = [
            i for i, c in enumerate(self._chunks) if self._filename_key(c.filename) != target_key
        ]
        self._chunks = [self._chunks[i] for i in keep_idx]
        if self._embeddings.size > 0:
            self._embeddings = self._embeddings[keep_idx]
        else:
            dim = int(self.dimension or 1024)
            self._embeddings = np.zeros((0, dim), dtype=np.float32)

        merged = "\n".join(t for t in texts if (t or "").strip()).strip()
        if not merged:
            self._rebuild_index()
            self._save()
            return 0

        parts = self._split_text(merged)
        if not parts:
            self._rebuild_index()
            self._save()
            return 0

        vecs = self._embed_texts(parts)
        if vecs.shape[0] != len(parts):
            raise RuntimeError("Embedding count mismatch while rebuilding chunks")

        new_chunks = [_Chunk(filename=filename_norm, text=part) for part in parts]
        if self._embeddings.size == 0:
            self._embeddings = vecs
        else:
            self._embeddings = np.vstack([self._embeddings, vecs]).astype(
                np.float32, copy=False
            )
        self._chunks.extend(new_chunks)
        self.dimension = int(self._embeddings.shape[1])
        self._rebuild_index()
        self._save()
        return len(new_chunks)

    def add_files(self, file_paths: Sequence[str]) -> int:
        """
        批量添加多个本地文件到知识库。
        
        逐个调用 add_text_file() 处理每个文件。支持所有 add_text_file() 支持的文件格式。
        
        参数说明：
            file_paths (Sequence[str])
                文件路径列表。可为相对路径或绝对路径。
                示例：["./docs/guide.pdf", "./docs/manual.pdf"]
                     ["/home/user/doc.txt", "C:\\\\docs\\\\file.docx"]
                
        返回值：
            int
                所有文件添加的总分片数。如果某文件处理失败，会自动跳过并继续处理下一个。
        
        异常处理：
            无异常抛出。如果某文件不存在或不可读，会自动跳过。
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> files = [
            ...     "./documents/guide.pdf",
            ...     "./documents/tutorial.md",
            ...     "./documents/reference.txt"
            ... ]
            >>> total_chunks = kb.add_files(files)
            >>> print(f"Added {total_chunks} chunks from {len(files)} files")
            
        处理流程：
            1. 遍历 file_paths 列表
            2. 对每个路径调用 add_text_file()
            3. 累计返回所有成功添加的分片数
            4. 任何单个文件的错误不会中断批处理
            
        性能提示：
            - 大批量文件（100+）会耗时较长
            - 处理期间知识库保持可用状态
            - 考虑使用 ingest_dir() 处理目录
        """
        total = 0
        for p in file_paths:
            total += self.add_text_file(p)
        return total

    def ingest_dir(
        self,
        root_dir: str,
        extensions: Sequence[str] = (
            ".pdf",
            ".ofd",
            ".xls",
            ".xlsx",
            ".xlsm",
            ".doc",
            ".docx",
            ".txt",
            ".md",
            ".rst",
            ".json",
            ".csv",
            ".log",
            ".wps",
            ".pws",
        ),
    ) -> int:
        """
        批量导入目录中的所有文件到知识库。
        
        该方法递归扫描指定目录及其所有子目录，找到所有匹配指定扩展名的文件，
        并依次通过 add_text_file() 添加到知识库中。
        
        工作流程：
            1. 验证目录存在性
            2. 规范化允许的文件扩展名（转换为小写）
            3. 递归遍历整个目录树
            4. 过滤符合扩展名的文件
            5. 逐文件处理，跳过损坏的文件，继续处理其他文件
            6. 返回成功处理的总块数
        
        参数说明：
            root_dir (str)
                目录的绝对路径或相对路径
                示例: "/data/documents" 或 "./knowledge_base/files"
                
            extensions (Sequence[str], 可选)
                允许处理的文件扩展名集合（不区分大小写）
                默认值包含常见格式: .pdf, .docx, .xlsx, .txt, .md 等
                示例: (".pdf", ".docx", ".xlsx")
                说明：
                    - 扩展名必须以 "." 开头
                    - 大小写不敏感（.PDF、.pdf、.Pdf 都会被匹配）
                    - 空列表表示导入所有文件（不推荐）
        
        返回值：
            int
            成功处理的总块数（所有文件的块数之和）
            说明：
                - 即使某个文件处理失败，返回值仍然是其他文件的块数总和
                - 返回 0 表示目录为空或没有找到匹配的文件
                - 返回值等于所有已成功处理文件的块数总和
        
        异常处理：
            FileNotFoundError
                当指定的目录路径不存在时抛出
                示例错误信息: "Directory not found: /nonexistent/path"
            
            其他异常（来自 add_text_file 调用）
                单个文件的处理错误不会中断整个导入过程
                该文件被跳过，继续处理后续文件
                错误信息会由 add_text_file 级别处理
        
        示例用法：
            >>> # 导入整个数据目录
            >>> kb = KnowledgeBase()
            >>> chunk_count = kb.ingest_dir("/data/documents")
            >>> print(f"导入了 {chunk_count} 个知识块")
            导入了 2345 个知识块
            
            >>> # 只导入特定类型的文件
            >>> chunk_count = kb.ingest_dir(
            ...     root_dir="/research/papers",
            ...     extensions=(".pdf", ".txt")
            ... )
            >>> print(f"从论文目录导入了 {chunk_count} 个块")
            从论文目录导入了 856 个块
            
            >>> # 导入包含多层子目录的项目
            >>> chunk_count = kb.ingest_dir(
            ...     root_dir="./project_docs",
            ...     extensions=(".md", ".rst", ".txt")
            ... )
            >>> print(f"文档总块数: {chunk_count}")
            文档总块数: 1234
        
        性能特性：
            - 时间复杂度：O(n)，其中 n 为所有目录和文件总数
            - 空间复杂度：O(m)，其中 m 为处理的文件数量
            - 适用规模：可处理数千个文件的目录
            - 建议：对于超过 10000 个文件的目录，考虑分批处理
        
        注意事项：
            - 目录扫描是递归的，会遍历所有子目录
            - 文件处理顺序与操作系统的遍历顺序有关（通常不保证特定顺序）
            - 导入期间知识库保持可用，查询和聊天操作不受影响
            - 大文件集处理时可能耗时较长（建议在后台任务中执行）
            - 推荐结合错误日志系统，追踪具体哪些文件处理失败
        """
        root = Path(root_dir)
        if not root.exists():
            raise FileNotFoundError(f"Directory not found: {root_dir}")

        allowed = {x.lower() for x in extensions}
        total = 0
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in allowed:
                continue
            total += self.add_text_file(str(p))
        return total

    def _candidate_search(
        self, query_vec: np.ndarray, top_n: int
    ) -> List[Tuple[int, float]]:
        if self._index is None or self._index.ntotal == 0:
            return []
        scores, indices = self._index.search(query_vec.astype(np.float32), top_n)
        out = []
        for idx, score in zip(indices[0].tolist(), scores[0].tolist()):
            if idx < 0:
                continue
            out.append((int(idx), float(score)))
        return out

    @staticmethod
    def _score_to_similarity(score: float) -> float:
        sim = float(score)
        if sim < 0:
            sim = 0.0
        if sim > 1:
            sim = 1.0
        return sim

    @staticmethod
    def _similarity_to_distance(similarity: float) -> float:
        sim = float(similarity)
        if sim <= 1e-12:
            return 1e12
        return (1.0 / sim) - 1.0

    def search(
        self, query: str, k: int | None = None, relevance_threshold: float | None = None
    ) -> List[Tuple[str, str, float]]:
        """
        搜索知识库，返回最相关的文本分片。
        
        使用多阶段检索和重排序策略：
        1. 第一阶段：使用嵌入模型编码查询，在 FAISS 索引中召回前 top_n 候选
        2. 第二阶段：使用重排序模型对候选重排，计算混合相似度分数
        3. 第三阶段：按相似度排序，过滤相关性阈值，去重，返回前 k 个结果
        
        参数说明：
            query (str)
                搜索查询文本。会被向量化进行语义相似性搜索。
                示例："如何学习 Python"、"knowledge base API"
                
            k (int, 可选)
                返回结果数量。默认值为 None（使用 self.default_k）。
                实际返回数可能少于 k，取决于：
                - 知识库中的总分片数
                - 相关性阈值过滤结果
                - 去重（同一文档只返回一个最相关分片）
                范围：[1, self.max_search_results]
                
            relevance_threshold (float, 可选)
                相关性阈值。值越小越严格。默认值：None（无阈值）。
                基于距离度量。范围：[0, ∞)，建议 [0.5, 2.0] 范围内。
                示例：threshold=1.0 只返回距离 ≤ 1.0 的结果
                
        返回值：
            List[Tuple[str, str, float]]
            返回列表，每个元素是 (filename, chunk_text, distance)：
            [
                ("document.pdf", "示例文本分片 1...", 0.523),
                ("guide.md", "示例文本分片 2...", 0.687),
                ...
            ]
            distance 为相关性距离，值越小表示越相关。
            
        异常处理：
            无异常抛出。当知识库为空时返回空列表。
        
        示例用法：
            >>> kb = KnowledgeBase()
            >>> kb.add_document("tutorial.md", "Python 是一门强大的编程语言...")
            >>> results = kb.search("Python 编程", k=3)
            >>> for filename, text, distance in results:
            ...     print(f"{filename}: {distance:.3f}")
            ...     print(f"  {text[:50]}...")
            
        高级示例：
            >>> # 严格相关性过滤
            >>> results = kb.search("机器学习", k=5, relevance_threshold=0.8)
            >>> # 查看搜索细节
            >>> logger.setLevel(logging.DEBUG)  # 查看日志信息
        
        搜索流程详解：
            1. 查询编码：text -> embedding vector
            2. 候选召回：用 FAISS 找前 (k * candidate_multiplier) 个候选
            3. 重排序：使用 Reranker 模型重新评分
            4. 混合评分：embed_weight * embed_score + rerank_weight * rerank_score
            5. 排序去重：按分数排序，去重取前 k 个
            6. 阈值过滤：如果 distance > threshold 则过滤
            7. 结果日志：打印搜索统计信息
        """
        logger.debug("开始搜索: query='%s', k=%s, relevance_threshold=%s", query[:50] if query and len(query) > 50 else query, k, relevance_threshold)
        
        if not self._chunks:
            logger.debug("知识库为空，返回空结果")
            return []

        query = (query or "").strip()
        if not query:
            logger.debug("查询文本为空，返回空结果")
            return []

        if k is None:
            k = self.default_k
        k = min(max(1, int(k)), self.max_search_results, len(self._chunks))
        logger.debug("实际搜索参数: k=%d, 总分片数=%d", k, len(self._chunks))
        if k <= 0:
            return []

        logger.debug("编码查询文本...")
        q_vec = self._embed_texts([query])
        if q_vec.shape[0] == 0:
            logger.debug("查询编码失败，返回空结果")
            return []
        logger.debug("查询编码完成，向量维度: %s", q_vec.shape)

        top_n = min(
            max(int(k) * self.candidate_multiplier, self.min_candidates, int(k)),
            len(self._chunks),
        )
        logger.debug("开始候选召回，召回数量: %d (k=%d, multiplier=%d)", top_n, k, self.candidate_multiplier)
        candidates = self._candidate_search(q_vec, top_n=top_n)
        if not candidates:
            logger.debug("未找到候选结果")
            return []
        logger.debug("召回 %d 个候选结果", len(candidates))

        if self.rerank_weight > 0:
            logger.debug("开始重排序，rerank_weight=%.2f", self.rerank_weight)
            cand_texts = [self._chunks[idx].text for idx, _ in candidates]
            rerank_raw = self._rerank_scores(query, cand_texts)
            ranked: List[Tuple[int, float]] = []
            for (idx, base_score), rr in zip(candidates, rerank_raw):
                base_sim = self._score_to_similarity(base_score)
                rr_sim = self._score_to_similarity(self._sigmoid(float(rr)))
                final_sim = self.embed_weight * base_sim + self.rerank_weight * rr_sim
                ranked.append((idx, self._score_to_similarity(final_sim)))
            logger.debug("重排序完成，得到 %d 个结果", len(ranked))
        else:
            logger.debug("跳过重排序（rerank_weight=0）")
            ranked = [(idx, self._score_to_similarity(score)) for idx, score in candidates]

        ranked.sort(key=lambda x: x[1], reverse=True)
        logger.debug("结果排序完成")

        threshold = None if relevance_threshold is None else float(relevance_threshold)
        results: List[Tuple[str, str, float]] = []
        seen_filenames: set[str] = set()
        
        logger.debug("开始过滤和去重，阈值=%s", threshold)
        for idx, sim in ranked:
            distance = self._similarity_to_distance(sim)
            if threshold is not None and distance > threshold:
                logger.debug("过滤结果 idx=%d (distance=%.4f > threshold=%.4f)", idx, distance, threshold)
                continue
            chunk = self._chunks[idx]
            filename_key = self._filename_key(chunk.filename)
            if filename_key in seen_filenames:
                logger.debug("去重结果 idx=%d (filename=%s 已存在)", idx, chunk.filename)
                continue
            seen_filenames.add(filename_key)
            results.append((chunk.filename, chunk.text, float(distance)))
            logger.debug("添加结果 #%d: filename=%s, distance=%.4f", len(results), chunk.filename, distance)
            if len(results) >= int(k):
                break
        
        logger.info(
            "Search completed: query_len=%s requested_k=%s returned=%s threshold=%s",
            len(query),
            k,
            len(results),
            relevance_threshold,
        )
        logger.debug("搜索完成，返回 %d 个结果", len(results))
        return results


def __getattr__(name: str):
    if name in {"KnowledgeBaseApi", "API"}:
        try:
            from .api import API, KnowledgeBaseApi
        except ImportError:  # pragma: no cover
            from api import API, KnowledgeBaseApi

        return {"KnowledgeBaseApi": KnowledgeBaseApi, "API": API}[name]
    if name == "Main":
        try:
            from .main import Main
        except ImportError:  # pragma: no cover
            from main import Main

        return Main
    raise AttributeError(name)
