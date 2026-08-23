"""
Universal LLM Client for multiple AI model providers.
Uses the OpenAI Python SDK for OpenAI-compatible model invocation.
"""
import logging
from typing import Any, Dict, Iterator, List, Sequence
from urllib.parse import urlparse, urlunparse

import numpy as np
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI


logger = logging.getLogger(__name__)


class UniversalLLMError(RuntimeError):
    """Exception raised for Universal LLM Client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class UniversalLLMClient:
    """Universal LLM Client supporting multiple OpenAI-compatible providers."""

    PROVIDER_ENDPOINTS = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3",
        "xai": "https://api.x.ai/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
        "kimi": "https://api.moonshot.cn/v1",
        "moonshot": "https://api.moonshot.cn/v1",
        "lm_studio": "http://localhost:1234/v1",
    }

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30,
        provider: str | None = None,
        extra_headers: Dict[str, str] | None = None,
    ):
        self.provider = provider or self._detect_provider(base_url)
        self.base_url = self._normalize_base_url(base_url, self.provider)
        self.api_key = api_key or None
        self.timeout = float(timeout)
        self.extra_headers = extra_headers or {}
        self.rerank_supported: bool | None = None
        self._client = self._build_sdk_client()

    @classmethod
    def from_provider(
        cls,
        provider: str,
        api_key: str | None = None,
        timeout: float = 30,
        **kwargs: Any,
    ) -> "UniversalLLMClient":
        base_url = cls.PROVIDER_ENDPOINTS.get(provider.lower())
        if not base_url:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(cls.PROVIDER_ENDPOINTS.keys())}"
            )
        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            provider=provider,
            **kwargs,
        )

    def _build_sdk_client(self) -> OpenAI:
        default_headers = dict(self.extra_headers)
        default_query: Dict[str, object] = {}
        sdk_api_key = self.api_key or "EMPTY"

        if self.provider == "gemini" and self.api_key:
            default_query["key"] = self.api_key
            default_headers.setdefault("Authorization", "")
            sdk_api_key = "EMPTY"

        return OpenAI(
            api_key=sdk_api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            default_headers=default_headers or None,
            default_query=default_query or None,
        )

    def _normalize_base_url(self, base_url: str, provider: str) -> str:
        normalized = str(base_url or "").strip().rstrip("/")
        parsed = urlparse(normalized)
        path = parsed.path.rstrip("/")
        hostname = (parsed.hostname or "").strip().lower()
        provider_lower = str(provider or "unknown").strip().lower()

        if hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
            if not path:
                path = "/v1"
            return urlunparse(parsed._replace(path=path))

        if provider_lower in {"openai", "deepseek", "xai", "kimi", "moonshot", "lm_studio"}:
            if not path:
                path = "/v1"
        elif provider_lower in {"qwen", "dashscope"}:
            if not path:
                path = "/compatible-mode/v1"
            elif path == "/compatible-mode":
                path = "/compatible-mode/v1"
        elif provider_lower == "gemini":
            if not path:
                path = "/v1beta"

        return urlunparse(parsed._replace(path=path))

    def _detect_provider(self, base_url: str) -> str:
        url_lower = base_url.lower()
        if "openai.com" in url_lower:
            return "openai"
        if "deepseek.com" in url_lower:
            return "deepseek"
        if "dashscope.aliyuncs.com" in url_lower or "aliyun" in url_lower:
            return "qwen"
        if "volces.com" in url_lower or "bytedance" in url_lower:
            return "doubao"
        if "x.ai" in url_lower:
            return "xai"
        if "generativelanguage.googleapis.com" in url_lower or "gemini" in url_lower:
            return "gemini"
        if "moonshot.cn" in url_lower or "kimi" in url_lower:
            return "kimi"
        if "localhost" in url_lower or "127.0.0.1" in url_lower:
            return "lm_studio"
        return "unknown"

    @staticmethod
    def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
        if vectors.size == 0:
            return vectors.astype(np.float32, copy=False)
        vectors = vectors.astype(np.float32, copy=False)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-12, None)
        return vectors / norms

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.provider != "gemini":
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers

    @staticmethod
    def _to_dict(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        model_dump = getattr(payload, "model_dump", None)
        if callable(model_dump):
            return model_dump(exclude_none=True)
        to_dict = getattr(payload, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        return {}

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

    def _raise_request_error(self, exc: Exception, path: str) -> None:
        status_code = getattr(exc, "status_code", None)
        message = str(exc)
        if isinstance(exc, APIStatusError):
            raise UniversalLLMError(
                f"API request failed ({status_code}) for {path}: {message}",
                status_code=status_code,
            ) from exc
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            raise UniversalLLMError(
                f"API request failed for {path}: {message}",
                status_code=None,
            ) from exc
        if isinstance(exc, APIError):
            raise UniversalLLMError(
                f"API request failed for {path}: {message}",
                status_code=status_code,
            ) from exc
        raise UniversalLLMError(
            f"API request failed for {path}: {message}",
            status_code=status_code,
        ) from exc

    def _extract_chat_text(self, resp: Dict[str, Any], *, include_reasoning: bool = False) -> str:
        choices = resp.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""

        message = first.get("message")
        if isinstance(message, dict):
            keys = ("content", "text") if not include_reasoning else ("content", "reasoning_content", "reasoning", "text")
            for key in keys:
                text = self._content_to_text(message.get(key))
                if text:
                    return text
            text_raw = message.get("text")
            if isinstance(text_raw, str) and text_raw:
                return text_raw

        text = first.get("text")
        if isinstance(text, str):
            return text
        return ""

    def _extract_stream_text(self, chunk: Dict[str, Any], *, include_reasoning: bool = False) -> str:
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""

        delta = first.get("delta")
        if isinstance(delta, dict):
            keys = ("content", "text") if not include_reasoning else ("content", "reasoning_content", "reasoning", "text")
            for key in keys:
                text = self._content_to_text(delta.get(key))
                if text:
                    return text
            text_raw = delta.get("text")
            if isinstance(text_raw, str) and text_raw:
                return text_raw

        message = first.get("message")
        if isinstance(message, dict):
            keys = ("content", "text") if not include_reasoning else ("content", "reasoning_content", "reasoning", "text")
            for key in keys:
                text = self._content_to_text(message.get(key))
                if text:
                    return text
            text_raw = message.get("text")
            if isinstance(text_raw, str) and text_raw:
                return text_raw

        text = first.get("text")
        if isinstance(text, str):
            return text
        return ""

    def _chat_request_kwargs(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        stream: bool,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": bool(stream),
            "timeout": self.timeout,
        }
        if temperature is not None:
            kwargs["temperature"] = float(temperature)
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)
        if extra:
            kwargs["extra_body"] = dict(extra)
        return kwargs

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("LLM request: provider=%s base_url=%s path=%s", self.provider, self.base_url, path)
        try:
            response = self._client.post(
                path,
                cast_to=dict,
                body=payload,
                options={"timeout": self.timeout},
            )
        except Exception as exc:
            self._raise_request_error(exc, path)
        return self._to_dict(response)

    def chat_once(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> str:
        logger.info("LLM chat request: provider=%s base_url=%s model=%s", self.provider, self.base_url, model)
        include_reasoning = bool(extra.pop("include_reasoning", False))
        try:
            response = self._client.chat.completions.create(
                **self._chat_request_kwargs(
                    messages=messages,
                    model=model,
                    stream=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra,
                )
            )
        except Exception as exc:
            self._raise_request_error(exc, "/chat/completions")

        resp_dict = self._to_dict(response)
        if isinstance(resp_dict.get("error"), dict):
            err = resp_dict.get("error") or {}
            message = str(err.get("message") or err.get("type") or "unknown provider error")
            raise UniversalLLMError(f"Chat request failed: {message}")
        text = self._extract_chat_text(resp_dict, include_reasoning=include_reasoning)
        if not text:
            raise UniversalLLMError("Chat response contains no text content")
        return text

    def chat_stream(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> Iterator[str]:
        logger.info("LLM stream request: provider=%s base_url=%s model=%s", self.provider, self.base_url, model)
        include_reasoning = bool(extra.pop("include_reasoning", False))
        yielded = False
        chunk_count = 0
        first_chunk_preview = ""

        try:
            stream = self._client.chat.completions.create(
                **self._chat_request_kwargs(
                    messages=messages,
                    model=model,
                    stream=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra,
                )
            )
            for chunk in stream:
                chunk_count += 1
                chunk_dict = self._to_dict(chunk)
                if chunk_count == 1:
                    try:
                        first_chunk_preview = f"keys={sorted(list(chunk_dict.keys()))}"
                    except Exception:
                        first_chunk_preview = "unavailable"
                if isinstance(chunk_dict.get("error"), dict):
                    err = chunk_dict.get("error") or {}
                    message = str(err.get("message") or err.get("type") or "unknown provider error")
                    logger.error(
                        "Upstream stream error chunk: provider=%s model=%s message=%s error=%s",
                        self.provider,
                        model,
                        message,
                        err,
                    )
                    raise UniversalLLMError(f"Chat stream failed: {message}")
                text = self._extract_stream_text(chunk_dict, include_reasoning=include_reasoning)
                if text:
                    yielded = True
                    yield text
        except UniversalLLMError:
            raise
        except Exception as exc:
            self._raise_request_error(exc, "/chat/completions")

        if not yielded:
            logger.error(
                "Upstream stream produced no text: provider=%s model=%s chunk_count=%d first_chunk=%s",
                self.provider,
                model,
                chunk_count,
                first_chunk_preview,
            )
            try:
                logger.warning(
                    "Stream had no text, fallback to chat_once: provider=%s model=%s",
                    self.provider,
                    model,
                )
                fallback_text = self.chat_once(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra,
                )
                fallback_text = str(fallback_text or "").strip()
                if fallback_text:
                    logger.info(
                        "Fallback chat_once succeeded: provider=%s model=%s length=%d",
                        self.provider,
                        model,
                        len(fallback_text),
                    )
                    yield fallback_text
                    return
            except Exception as exc:
                logger.error(
                    "Fallback chat_once failed: provider=%s model=%s error=%s",
                    self.provider,
                    model,
                    exc,
                )
            raise UniversalLLMError("Chat stream ended without text chunks")

    def embed_texts(self, texts: Sequence[str], model: str) -> np.ndarray:
        try:
            response = self._client.embeddings.create(
                input=list(texts),
                model=model,
                timeout=self.timeout,
            )
        except Exception as exc:
            self._raise_request_error(exc, "/embeddings")

        resp_dict = self._to_dict(response)
        data = resp_dict.get("data", [])
        if not isinstance(data, list):
            raise UniversalLLMError("Embeddings response missing data")

        try:
            data = sorted(data, key=lambda item: item.get("index", 0))
        except Exception:
            pass

        vectors = [item.get("embedding", []) for item in data]
        if len(vectors) != len(texts):
            raise UniversalLLMError("Embeddings count mismatch")

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
            raise UniversalLLMError("Rerank response missing scores")

        if not isinstance(items, list):
            raise UniversalLLMError("Rerank response invalid format")

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
            fill_value = min(found_scores) - 1.0 if found_scores else 0.0
            scores = [score if score is not None else fill_value for score in scores]
            return [float(score) for score in scores]

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
            raise UniversalLLMError("Rerank count mismatch")
        return scores_seq

    def rerank_scores(self, query: str, docs: Sequence[str], model: str) -> List[float] | None:
        payload = {
            "model": model,
            "query": query,
            "documents": list(docs),
            "top_n": len(docs),
            "return_documents": False,
        }
        try:
            resp = self._post("/rerank", payload)
        except UniversalLLMError as exc:
            if exc.status_code in {400, 404}:
                self.rerank_supported = False
                return None
            raise

        self.rerank_supported = True
        return self._parse_rerank_response(resp, expected=len(docs))


LmStudioClient = UniversalLLMClient
LmStudioRequestError = UniversalLLMError
