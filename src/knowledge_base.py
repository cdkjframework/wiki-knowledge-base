import json
import math
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from xml.etree import ElementTree as ET

import faiss
import numpy as np
import pandas as pd
import torch

from .lm_studio_client import LmStudioClient

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None

_BINARY_TEXT_RE = re.compile(rb"[ -~]{4,}")


@dataclass
class _Chunk:
    filename: str
    text: str


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
        chunk_cfg = kb_cfg.get("chunking", {}) if isinstance(kb_cfg.get("chunking"), dict) else {}
        retrieval_cfg = (
            kb_cfg.get("retrieval", {}) if isinstance(kb_cfg.get("retrieval"), dict) else {}
        )

        cfg_persist_dir = storage_cfg.get("persist_dir", kb_cfg.get("persist_dir", "kb_store"))
        cfg_embed = embedding_cfg.get(
            "model", kb_cfg.get("embedding_model", "Qwen/Qwen3-Embedding-0.6B")
        )
        cfg_rerank = rerank_cfg.get(
            "model", kb_cfg.get("reranker_model", "Qwen/Qwen3-Reranker-0.6B")
        )
        cfg_dimension = embedding_cfg.get("dimension", kb_cfg.get("dimension"))
        cfg_device = embedding_cfg.get("device", kb_cfg.get("device", "auto"))
        cfg_local_only = embedding_cfg.get("local_files_only", kb_cfg.get("local_files_only"))
        cfg_lm_base = lm_cfg.get("base_url", kb_cfg.get("lm_studio_base_url"))
        cfg_lm_api_key = lm_cfg.get("api_key", kb_cfg.get("lm_studio_api_key"))
        cfg_lm_timeout = lm_cfg.get("timeout", kb_cfg.get("lm_studio_timeout", 30))
        cfg_lm_embed = embedding_cfg.get(
            "use_lm_studio", kb_cfg.get("use_lm_studio_embeddings")
        )
        cfg_lm_rerank = rerank_cfg.get("use_lm_studio", kb_cfg.get("use_lm_studio_rerank"))
        cfg_chunk_size = chunk_cfg.get("size", kb_cfg.get("chunk_size", 800))
        cfg_chunk_overlap = chunk_cfg.get("overlap", kb_cfg.get("chunk_overlap", 120))
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

        self.persist_dir = Path(persist_dir or cfg_persist_dir)
        self.meta_path = self.persist_dir / "meta.json"
        self.chunks_path = self.persist_dir / "chunks.jsonl"
        self.embeddings_path = self.persist_dir / "embeddings.npy"
        self.index_path = self.persist_dir / "index.faiss"

        self.embedding_model_name = embedding_model or os.getenv("KB_EMBED_MODEL", cfg_embed)
        self.reranker_model_name = reranker_model or os.getenv("KB_RERANK_MODEL", cfg_rerank)
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
                self.local_files_only = local_only_env in {"1", "true", "yes", "on"}
        else:
            self.local_files_only = bool(local_files_only)

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
            self.use_lm_studio_embeddings = bool(self.lm_studio_base_url)
        if isinstance(cfg_lm_rerank, bool):
            self.use_lm_studio_rerank = cfg_lm_rerank
        else:
            self.use_lm_studio_rerank = bool(self.lm_studio_base_url)

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

        self._chunks: List[_Chunk] = []
        self._embeddings = np.zeros((0, 1), dtype=np.float32)
        self._index = None

        self._load()

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
        if self._index is not None:
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
                    chunks.append(_Chunk(filename=obj["filename"], text=obj["text"]))
            self._chunks = chunks

        if self.embeddings_path.exists():
            emb = np.load(self.embeddings_path)
            if emb.ndim == 2:
                self._embeddings = emb.astype(np.float32, copy=False)
                if self._embeddings.shape[0] > 0:
                    self.dimension = int(self._embeddings.shape[1])

        if (
            len(self._chunks) == 0
            or self._embeddings.ndim != 2
            or len(self._chunks) != self._embeddings.shape[0]
        ):
            if self.dimension is None:
                self.dimension = 1024
            self._chunks = []
            self._embeddings = np.zeros((0, self.dimension), dtype=np.float32)
            self._index = None
            self._save()
            return

        if self.index_path.exists():
            try:
                self._index = faiss.read_index(str(self.index_path))
            except Exception:
                self._rebuild_index()
        else:
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
        )
        self._embed_model = AutoModel.from_pretrained(
            self.embedding_model_name,
            trust_remote_code=True,
            local_files_only=self.local_files_only,
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
        )
        try:
            self._rerank_model = AutoModelForSequenceClassification.from_pretrained(
                self.reranker_model_name,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
            )
        except Exception:
            self._rerank_model = AutoModel.from_pretrained(
                self.reranker_model_name,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
            )
        self._rerank_model.to(self.device)
        self._rerank_model.eval()

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
                logits = outputs.logits
                if logits.ndim == 2 and logits.shape[1] > 1:
                    vals = logits[:, -1]
                else:
                    vals = logits.squeeze(-1)
            else:
                vals = outputs[0].squeeze(-1)
            scores.extend([float(x) for x in vals.detach().cpu().tolist()])
        return scores

    def _rebuild_index(self) -> None:
        if self.dimension is None:
            self.dimension = 1024
        if self._embeddings.size == 0:
            self._index = faiss.IndexFlatIP(int(self.dimension))
            return
        self._index = faiss.IndexFlatIP(int(self._embeddings.shape[1]))
        self._index.add(self._embeddings.astype(np.float32, copy=False))

    def clear(self) -> None:
        if self.dimension is None:
            self.dimension = 1024
        self._chunks = []
        self._embeddings = np.zeros((0, int(self.dimension)), dtype=np.float32)
        self._rebuild_index()
        self._save()

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
        text = (text or "").strip()
        if not text:
            return 0

        keep_idx = [i for i, c in enumerate(self._chunks) if c.filename != filename]
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

        new_chunks = [_Chunk(filename=filename, text=part) for part in parts]
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
        return self.add_document(path.name, text)

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

    def search(
        self, query: str, k: int = 3, relevance_threshold: float = 1.0
    ) -> List[Tuple[str, str, float]]:
        if not self._chunks:
            return []

        query = (query or "").strip()
        if not query:
            return []

        q_vec = self._embed_texts([query])
        if q_vec.shape[0] == 0:
            return []

        top_n = min(
            max(int(k) * self.candidate_multiplier, self.min_candidates), len(self._chunks)
        )
        candidates = self._candidate_search(q_vec, top_n=top_n)
        candidates = [x for x in candidates if x[1] >= float(relevance_threshold)]
        if not candidates:
            return []

        cand_texts = [self._chunks[idx].text for idx, _ in candidates]
        rerank_raw = self._rerank_scores(query, cand_texts)

        merged = []
        for (idx, base_score), rr in zip(candidates, rerank_raw):
            rr_norm = self._sigmoid(float(rr))
            final_score = self.embed_weight * float(base_score) + self.rerank_weight * rr_norm
            chunk = self._chunks[idx]
            merged.append((chunk.filename, chunk.text, final_score))

        merged.sort(key=lambda x: x[2], reverse=True)
        return merged[: max(1, int(k))]
