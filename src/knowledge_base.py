import json
import logging
import math
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from xml.etree import ElementTree as ET

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None
import numpy as np
try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None
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
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None

_BINARY_TEXT_RE = re.compile(rb"[ -~]{4,}")
logger = logging.getLogger(__name__)


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


class KnowledgeBase:
    """
    Local knowledge base with:
    - Qwen3 Embedding for recall
    - Qwen3 Reranker for rerank
    - FAISS for vector search

    Public search contract:
    search(query, k=3, relevance_threshold=1.0) -> List[(filename, chunk_text, score)]
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
        config = self._load_project_config()
        kb_cfg = config.get("knowledge_base", {})
        storage_cfg = kb_cfg.get("storage", {}) if isinstance(kb_cfg.get("storage"), dict) else {}
        embedding_cfg = (
            kb_cfg.get("embedding", {}) if isinstance(kb_cfg.get("embedding"), dict) else {}
        )
        rerank_cfg = kb_cfg.get("rerank", {}) if isinstance(kb_cfg.get("rerank"), dict) else {}
        lm_cfg = kb_cfg.get("lm_studio", {}) if isinstance(kb_cfg.get("lm_studio"), dict) else {}
        chat_cfg = kb_cfg.get("chat", {}) if isinstance(kb_cfg.get("chat"), dict) else {}
        chunk_cfg = kb_cfg.get("chunking", {}) if isinstance(kb_cfg.get("chunking"), dict) else {}
        search_cfg = config.get("search", {}) if isinstance(config.get("search"), dict) else {}
        retrieval_cfg = (
            kb_cfg.get("retrieval", {}) if isinstance(kb_cfg.get("retrieval"), dict) else {}
        )
        project_root = Path(__file__).resolve().parent.parent

        cfg_persist_dir = storage_cfg.get("persist_dir", kb_cfg.get("persist_dir", "./kb_store"))
        cfg_model_cache_dir = storage_cfg.get("model_cache_dir", kb_cfg.get("model_cache_dir"))
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
        self.index_path = self.persist_dir / "index.faiss"

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
                    self.local_files_only = True
        else:
            self.local_files_only = bool(local_files_only)
        self._configure_hf_offline_mode()

        if device:
            self.device = device
        else:
            if str(cfg_device).lower() == "auto":
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                self.device = str(cfg_device)

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

        self._chunks: List[_Chunk] = []
        self._embeddings = np.zeros((0, 1), dtype=np.float32)
        self._index = None

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
            return
        # Keep HuggingFace stack fully offline when local cache mode is enabled.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    @staticmethod
    def _normalize_filename(name: str | None) -> str:
        return Path(str(name or "").strip()).name

    @staticmethod
    def _filename_key(name: str | None) -> str:
        return KnowledgeBase._normalize_filename(name).lower()

    @staticmethod
    def _load_project_config() -> Dict[str, Any]:
        project_root = Path(__file__).resolve().parent.parent
        config_path = project_root / "config.json"
        if not config_path.exists():
            return {}
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

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
        if self._index is not None and faiss is not None:
            faiss.write_index(self._index, str(self.index_path))

    def _load(self) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        if self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            if not self.dimension and meta.get("dimension"):
                self.dimension = int(meta["dimension"])

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

        if self.index_path.exists() and faiss is not None:
            try:
                self._index = faiss.read_index(str(self.index_path))
            except Exception:
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
        self._embed_tokenizer = AutoTokenizer.from_pretrained(
            self.embedding_model_name,
            trust_remote_code=True,
            local_files_only=self.local_files_only,
            cache_dir=str(self.model_cache_dir),
        )
        self._embed_model = AutoModel.from_pretrained(
            self.embedding_model_name,
            trust_remote_code=True,
            local_files_only=self.local_files_only,
            cache_dir=str(self.model_cache_dir),
        )
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
        self._rerank_tokenizer = AutoTokenizer.from_pretrained(
            self.reranker_model_name,
            trust_remote_code=True,
            local_files_only=self.local_files_only,
            cache_dir=str(self.model_cache_dir),
        )
        try:
            # Prefer model's native implementation (often provides compute_score for reranker).
            self._rerank_model = AutoModel.from_pretrained(
                self.reranker_model_name,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
                cache_dir=str(self.model_cache_dir),
            )
        except Exception:
            self._rerank_model = AutoModelForSequenceClassification.from_pretrained(
                self.reranker_model_name,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
                cache_dir=str(self.model_cache_dir),
            )
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
        chosen_model = str(model or self.chat_model_name or "").strip()
        if not chosen_model:
            raise RuntimeError("No chat model configured")
        return self._chat_backend.chat_once(
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

    def _embed_texts(self, texts: Sequence[str], batch_size: int = 16) -> np.ndarray:
        if self.use_lm_studio_embeddings and self._lm_client is not None:
            vecs = self._lm_client.embed_texts(texts, model=self.embedding_model_name)
            if vecs.shape[0] > 0 and self.dimension is None:
                self.dimension = int(vecs.shape[1])
            return vecs
        self._ensure_embed_model()
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
        return vectors

    def _rerank_scores(self, query: str, docs: Sequence[str], batch_size: int = 8) -> List[float]:
        if (
            self.use_lm_studio_rerank
            and self._lm_client is not None
            and self._lm_client.rerank_supported is not False
        ):
            scores = self._lm_client.rerank_scores(
                query, docs, model=self.reranker_model_name
            )
            if scores is not None:
                return scores
        self._ensure_reranker_model()
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
        return scores

    def _rebuild_index(self) -> None:
        if self.dimension is None:
            self.dimension = 1024
        if self._embeddings.size == 0:
            if faiss is not None:
                self._index = faiss.IndexFlatIP(int(self.dimension))
            else:
                self._index = _NumpyIndexFlatIP(int(self.dimension))
            return
        if faiss is not None:
            self._index = faiss.IndexFlatIP(int(self._embeddings.shape[1]))
        else:
            self._index = _NumpyIndexFlatIP(int(self._embeddings.shape[1]))
        self._index.add(self._embeddings.astype(np.float32, copy=False))

    def clear(self) -> None:
        if self.dimension is None:
            self.dimension = 1024
        self._chunks = []
        self._embeddings = np.zeros((0, int(self.dimension)), dtype=np.float32)
        self._rebuild_index()
        self._save()

    def remove_document(self, filename: str) -> int:
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
        dim = self.dimension
        if dim is None and self._embeddings.ndim == 2 and self._embeddings.shape[1] > 0:
            dim = int(self._embeddings.shape[1])
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
        }

    def warmup_models(
        self, load_embedding: bool = True, load_reranker: bool = True
    ) -> Dict[str, Any]:
        status: Dict[str, Any] = {"embedding_loaded": False, "reranker_loaded": False}

        if load_embedding:
            try:
                if self.use_lm_studio_embeddings and self._lm_client is not None:
                    self._lm_client.embed_texts(["warmup"], model=self.embedding_model_name)
                else:
                    self._ensure_embed_model()
                status["embedding_loaded"] = True
            except Exception as exc:
                status["embedding_error"] = str(exc)
                logger.exception("Embedding warmup failed")

        if load_reranker:
            try:
                if self.use_lm_studio_rerank and self._lm_client is not None:
                    self._lm_client.rerank_scores(
                        "warmup",
                        ["warmup"],
                        model=self.reranker_model_name,
                    )
                else:
                    self._ensure_reranker_model()
                status["reranker_loaded"] = True
            except Exception as exc:
                status["reranker_error"] = str(exc)
                logger.exception("Reranker warmup failed")

        logger.info("Warmup result: %s", status)
        return status

    def _split_text(self, text: str) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        step = max(1, self.chunk_size - self.chunk_overlap)
        start = 0
        while start < len(text):
            part = text[start : start + self.chunk_size].strip()
            if part:
                chunks.append(part)
            if start + self.chunk_size >= len(text):
                break
            start += step
        return chunks

    @staticmethod
    def _read_text(path: Path) -> str:
        for enc in ("utf-8", "gb18030", "latin-1"):
            try:
                return path.read_text(encoding=enc, errors="ignore")
            except Exception:
                continue
        return ""

    @staticmethod
    def _extract_text_from_xml_bytes(data: bytes) -> str:
        try:
            root = ET.fromstring(data)
        except Exception:
            return ""

        vals = []
        for elem in root.iter():
            if elem.text:
                t = elem.text.strip()
                if t:
                    vals.append(t)
        return "\n".join(vals)

    def _read_pdf(self, path: Path) -> str:
        if PdfReader is None:
            return ""
        try:
            reader = PdfReader(str(path))
        except Exception:
            return ""
        lines = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                lines.append(text)
        return "\n".join(lines)

    def _read_docx(self, path: Path) -> str:
        if Document is None:
            return ""
        try:
            doc = Document(str(path))
        except Exception:
            return ""
        lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(lines)

    def _read_doc(self, path: Path) -> str:
        try:
            import subprocess

            result = subprocess.run(
                ["antiword", str(path)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception:
            pass
        return self._read_binary_strings(path)

    def _read_excel(self, path: Path) -> str:
        if pd is None:
            return self._read_binary_strings(path)
        try:
            sheets = pd.read_excel(path, sheet_name=None, header=None)
        except Exception:
            return self._read_binary_strings(path)

        rows = []
        for sheet_name, df in sheets.items():
            rows.append(f"# Sheet: {sheet_name}")
            for row in df.fillna("").astype(str).values.tolist():
                vals = [x.strip() for x in row if x and x.strip()]
                if vals:
                    rows.append(" | ".join(vals))
        return "\n".join(rows)

    def _read_ofd(self, path: Path) -> str:
        if not zipfile.is_zipfile(path):
            return self._read_binary_strings(path)

        texts = []
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for name in zf.namelist():
                    lower = name.lower()
                    if not lower.endswith(".xml"):
                        continue
                    try:
                        data = zf.read(name)
                    except Exception:
                        continue
                    txt = self._extract_text_from_xml_bytes(data)
                    if txt.strip():
                        texts.append(txt)
        except Exception:
            return self._read_binary_strings(path)
        return "\n".join(texts)

    def _read_pws(self, path: Path) -> str:
        if zipfile.is_zipfile(path):
            return self._read_ofd(path)
        return self._read_binary_strings(path)

    @staticmethod
    def _read_binary_strings(path: Path) -> str:
        try:
            raw = path.read_bytes()
        except Exception:
            return ""

        candidates = []
        for enc in ("utf-8", "gb18030", "utf-16le", "latin-1"):
            try:
                s = raw.decode(enc, errors="ignore")
                if s:
                    candidates.append(s)
            except Exception:
                continue

        ascii_strings = [m.decode("ascii", errors="ignore") for m in _BINARY_TEXT_RE.findall(raw)]
        if ascii_strings:
            candidates.append("\n".join(ascii_strings))

        if not candidates:
            return ""
        candidates.sort(key=lambda x: len(x), reverse=True)
        return candidates[0]

    def _extract_text(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in {
            ".txt",
            ".md",
            ".rst",
            ".json",
            ".csv",
            ".log",
            ".py",
            ".yaml",
            ".yml",
        }:
            return self._read_text(path)
        if ext == ".pdf":
            return self._read_pdf(path)
        if ext == ".ofd":
            return self._read_ofd(path)
        if ext in {".xls", ".xlsx", ".xlsm"}:
            return self._read_excel(path)
        if ext == ".docx":
            return self._read_docx(path)
        if ext in {".doc", ".wps"}:
            return self._read_doc(path)
        if ext in {".pws"}:
            return self._read_pws(path)
        return self._read_binary_strings(path)

    def add_document(self, filename: str, text: str) -> int:
        filename_norm = self._normalize_filename(filename)
        if not filename_norm:
            raise ValueError("filename is required")
        text = (text or "").strip()
        if not text:
            return 0

        target_key = self._filename_key(filename_norm)
        keep_idx = [i for i, c in enumerate(self._chunks) if self._filename_key(c.filename) != target_key]
        if len(keep_idx) != len(self._chunks):
            self._chunks = [self._chunks[i] for i in keep_idx]
            self._embeddings = self._embeddings[keep_idx]

        parts = self._split_text(text)
        if not parts:
            self._rebuild_index()
            self._save()
            return 0

        vecs = self._embed_texts(parts)
        if vecs.shape[0] != len(parts):
            raise RuntimeError("Embedding count mismatch while adding document")

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

    def add_text_file(self, file_path: str) -> int:
        path = Path(file_path)
        text = self._extract_text(path)
        return self.add_document(self._normalize_filename(path.name), text)

    @staticmethod
    def _decode_uploaded_text_bytes(data: bytes, encoding: str | None = None) -> str:
        if encoding:
            try:
                return data.decode(encoding)
            except Exception as exc:
                raise ValueError(f"Unable to decode file with encoding: {encoding}") from exc
        for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "utf-16le", "utf-16be"):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode("utf-8", errors="replace")

    def add_uploaded_file(
        self, filename: str, content: bytes, encoding: str | None = None
    ) -> int:
        filename_clean = self._normalize_filename(filename)
        if not filename_clean:
            raise ValueError("filename is required")
        data = bytes(content or b"")
        if not data:
            return 0

        ext = Path(filename_clean).suffix.lower()
        text_exts = {
            ".txt",
            ".md",
            ".rst",
            ".json",
            ".csv",
            ".log",
            ".py",
            ".yaml",
            ".yml",
        }

        if encoding is not None or ext in text_exts:
            text = self._decode_uploaded_text_bytes(data, encoding=encoding)
            return self.add_document(filename_clean, text)

        upload_tmp_dir = self.persist_dir / ".upload_tmp"
        upload_tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=(ext or ".bin"),
                dir=str(upload_tmp_dir),
                delete=False,
            ) as fp:
                fp.write(data)
                tmp_path = Path(fp.name)
            text = self._extract_text(tmp_path)
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

        if not (text or "").strip():
            text = self._decode_uploaded_text_bytes(data, encoding=encoding)
        return self.add_document(filename_clean, text)

    def add_files(self, file_paths: Sequence[str]) -> int:
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
        if not self._chunks:
            return []

        query = (query or "").strip()
        if not query:
            return []

        if k is None:
            k = self.default_k
        k = min(max(1, int(k)), self.max_search_results, len(self._chunks))
        if k <= 0:
            return []

        q_vec = self._embed_texts([query])
        if q_vec.shape[0] == 0:
            return []

        top_n = min(
            max(int(k) * self.candidate_multiplier, self.min_candidates, int(k)),
            len(self._chunks),
        )
        candidates = self._candidate_search(q_vec, top_n=top_n)
        if not candidates:
            return []

        if self.rerank_weight > 0:
            cand_texts = [self._chunks[idx].text for idx, _ in candidates]
            rerank_raw = self._rerank_scores(query, cand_texts)
            ranked: List[Tuple[int, float]] = []
            for (idx, base_score), rr in zip(candidates, rerank_raw):
                base_sim = self._score_to_similarity(base_score)
                rr_sim = self._score_to_similarity(self._sigmoid(float(rr)))
                final_sim = self.embed_weight * base_sim + self.rerank_weight * rr_sim
                ranked.append((idx, self._score_to_similarity(final_sim)))
        else:
            ranked = [(idx, self._score_to_similarity(score)) for idx, score in candidates]

        ranked.sort(key=lambda x: x[1], reverse=True)

        threshold = None if relevance_threshold is None else float(relevance_threshold)
        results: List[Tuple[str, str, float]] = []
        seen_filenames: set[str] = set()
        for idx, sim in ranked:
            distance = self._similarity_to_distance(sim)
            if threshold is not None and distance > threshold:
                continue
            chunk = self._chunks[idx]
            filename_key = self._filename_key(chunk.filename)
            if filename_key in seen_filenames:
                continue
            seen_filenames.add(filename_key)
            results.append((chunk.filename, chunk.text, float(distance)))
            if len(results) >= int(k):
                break
        logger.info(
            "Search completed: query_len=%s requested_k=%s returned=%s threshold=%s",
            len(query),
            k,
            len(results),
            relevance_threshold,
        )
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
