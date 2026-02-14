import json
from typing import Any, Dict, Iterator, List, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np


class LmStudioRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LmStudioClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None
        self.timeout = float(timeout)
        self.rerank_supported: bool | None = None

    @staticmethod
    def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
        if vectors.size == 0:
            return vectors.astype(np.float32, copy=False)
        vectors = vectors.astype(np.float32, copy=False)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-12, None)
        return vectors / norms

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = Request(url, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                err_body = ""
            raise LmStudioRequestError(
                f"LM Studio request failed ({exc.code}) for {path}: {err_body or exc.reason}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise LmStudioRequestError(
                f"LM Studio request failed for {path}: {exc}",
                status_code=None,
            ) from exc

        text = raw.decode("utf-8", errors="ignore").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception as exc:
            raise LmStudioRequestError(
                f"LM Studio returned invalid JSON for {path}"
            ) from exc

    def _stream_post_json(self, path: str, payload: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = Request(url, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        payload_text = line[5:].strip()
                    else:
                        payload_text = line
                    if payload_text == "[DONE]":
                        break
                    if not payload_text:
                        continue
                    try:
                        yield json.loads(payload_text)
                    except Exception as exc:
                        raise LmStudioRequestError(
                            f"LM Studio returned invalid streaming JSON for {path}: {payload_text[:200]}"
                        ) from exc
        except HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                err_body = ""
            raise LmStudioRequestError(
                f"LM Studio request failed ({exc.code}) for {path}: {err_body or exc.reason}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise LmStudioRequestError(
                f"LM Studio request failed for {path}: {exc}",
                status_code=None,
            ) from exc

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)
        return ""

    def _extract_chat_text(self, resp: Dict[str, Any]) -> str:
        choices = resp.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if isinstance(message, dict):
            text = self._content_to_text(message.get("content"))
            if text:
                return text
        text = first.get("text")
        if isinstance(text, str):
            return text
        return ""

    def _extract_stream_text(self, chunk: Dict[str, Any]) -> str:
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        delta = first.get("delta")
        if isinstance(delta, dict):
            text = self._content_to_text(delta.get("content"))
            if text:
                return text
        message = first.get("message")
        if isinstance(message, dict):
            text = self._content_to_text(message.get("content"))
            if text:
                return text
        text = first.get("text")
        if isinstance(text, str):
            return text
        return ""

    def _build_chat_payload(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        stream: bool,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": bool(stream),
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        payload.update(extra)
        return payload

    def chat_once(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> str:
        payload = self._build_chat_payload(
            messages=messages,
            model=model,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
        resp = self._post("/v1/chat/completions", payload)
        return self._extract_chat_text(resp)

    def chat_stream(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> Iterator[str]:
        payload = self._build_chat_payload(
            messages=messages,
            model=model,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
        for chunk in self._stream_post_json("/v1/chat/completions", payload):
            text = self._extract_stream_text(chunk)
            if text:
                yield text

    def embed_texts(self, texts: Sequence[str], model: str) -> np.ndarray:
        payload = {"model": model, "input": list(texts)}
        resp = self._post("/v1/embeddings", payload)
        data = resp.get("data", [])
        if not isinstance(data, list):
            raise LmStudioRequestError("LM Studio embeddings response missing data")
        try:
            data = sorted(data, key=lambda d: d.get("index", 0))
        except Exception:
            pass
        vectors = [item.get("embedding", []) for item in data]
        if len(vectors) != len(texts):
            raise LmStudioRequestError("LM Studio embeddings count mismatch")
        vecs = np.asarray(vectors, dtype=np.float32)
        return self._normalize_rows(vecs)

    def _parse_rerank_response(self, resp: Dict[str, Any], expected: int) -> List[float]:
        if isinstance(resp, dict) and "results" in resp:
            items = resp["results"]
        elif isinstance(resp, dict) and "data" in resp:
            items = resp["data"]
        elif isinstance(resp, dict) and "scores" in resp:
            scores = resp["scores"]
            return [float(x) for x in scores]
        else:
            raise LmStudioRequestError("LM Studio rerank response missing scores")

        if not isinstance(items, list):
            raise LmStudioRequestError("LM Studio rerank response invalid format")

        scores: List[float | None] = [None] * expected
        found_scores: List[float] = []
        have_index = True
        for item in items:
            if isinstance(item, dict):
                idx = item.get("index")
                score = item.get("relevance_score", item.get("score"))
            else:
                idx = None
                score = item
            if idx is None:
                have_index = False
                break
            try:
                idx_int = int(idx)
            except Exception:
                have_index = False
                break
            if 0 <= idx_int < expected:
                try:
                    val = float(score)
                except Exception:
                    val = 0.0
                scores[idx_int] = val
                found_scores.append(val)

        if have_index:
            if found_scores:
                fill_value = min(found_scores) - 1.0
            else:
                fill_value = 0.0
            scores = [s if s is not None else fill_value for s in scores]
            return [float(x) for x in scores]

        scores_seq: List[float] = []
        for item in items:
            if isinstance(item, dict):
                score = item.get("relevance_score", item.get("score"))
            else:
                score = item
            try:
                scores_seq.append(float(score))
            except Exception:
                scores_seq.append(0.0)
        if len(scores_seq) != expected:
            raise LmStudioRequestError("LM Studio rerank count mismatch")
        return scores_seq

    def rerank_scores(
        self, query: str, docs: Sequence[str], model: str
    ) -> List[float] | None:
        payload = {
            "model": model,
            "query": query,
            "documents": list(docs),
            "top_n": len(docs),
            "return_documents": False,
        }
        try:
            resp = self._post("/v1/rerank", payload)
        except LmStudioRequestError as exc:
            if exc.status_code in {400, 404}:
                self.rerank_supported = False
                return None
            raise
        self.rerank_supported = True
        return self._parse_rerank_response(resp, expected=len(docs))
