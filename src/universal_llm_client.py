"""
Universal LLM Client for multiple AI model providers
Supports: OpenAI, DeepSeek, Qwen (通义千问), Doubao (豆包), GPT, xAI, Gemini, Kimi, and more
"""
import json
import logging
from typing import Any, Dict, Iterator, List, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import requests


logger = logging.getLogger(__name__)


class UniversalLLMError(RuntimeError):
    """Exception raised for Universal LLM Client errors"""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class UniversalLLMClient:
    """
    Universal LLM Client supporting multiple AI providers
    
    Supported providers:
    - OpenAI (GPT-3.5, GPT-4, etc.)
    - DeepSeek (deepseek-chat, deepseek-coder)
    - Qwen / 通义千问 (qwen-turbo, qwen-plus, qwen-max)
    - Doubao / 豆包 (ByteDance's LLM)
    - xAI (Grok)
    - Google Gemini (gemini-pro, gemini-ultra)
    - Moonshot / Kimi (moonshot-v1)
    - LM Studio (local deployment)
    - Any OpenAI-compatible API
    
    Provider Configuration Examples:
    
    1. OpenAI:
       base_url="https://api.openai.com"
       api_key="sk-..."
       model="gpt-4"
    
    2. DeepSeek:
       base_url="https://api.deepseek.com"
       api_key="sk-..."
       model="deepseek-chat"
    
    3. Qwen (DashScope):
       base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
       api_key="sk-..."
       model="qwen-turbo"
    
    4. Doubao (ByteDance):
       base_url="https://ark.cn-beijing.volces.com/api/v3"
       api_key="..."
       model="doubao-pro-32k"
    
    5. xAI:
       base_url="https://api.x.ai/v1"
       api_key="xai-..."
       model="grok-beta"
    
    6. Gemini:
       base_url="https://generativelanguage.googleapis.combeta"
       api_key="..."
       model="gemini-pro"
    
    7. Kimi (Moonshot):
       base_url="https://api.moonshot.cn/v1"
       api_key="sk-..."
       model="moonshot-v1-8k"
    
    8. LM Studio (Local):
       base_url="http://localhost:1234/v1"
       api_key=None
       model="local-model"
    """
    
    # Provider-specific API endpoints
    PROVIDER_ENDPOINTS = {
        "openai": "https://api.openai.com",
        "deepseek": "https://api.deepseek.com",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3",
        "xai": "https://api.x.ai/v1",
        "gemini": "https://generativelanguage.googleapis.combeta",
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
        """
        Initialize Universal LLM Client
        
        Args:
            base_url: Base URL of the API endpoint
            api_key: API key for authentication (optional for local models)
            timeout: Request timeout in seconds
            provider: Provider name (openai, deepseek, qwen, etc.) - auto-detected if not specified
            extra_headers: Additional HTTP headers to include in requests
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None
        self.timeout = float(timeout)
        self.provider = provider or self._detect_provider(base_url)
        self.extra_headers = extra_headers or {}
        self.rerank_supported: bool | None = None

    @classmethod
    def from_provider(
        cls,
        provider: str,
        api_key: str | None = None,
        timeout: float = 30,
        **kwargs: Any,
    ) -> "UniversalLLMClient":
        """
        Create client from provider name
        
        Args:
            provider: Provider name (openai, deepseek, qwen, kimi, etc.)
            api_key: API key
            timeout: Request timeout
            **kwargs: Additional arguments
        
        Returns:
            UniversalLLMClient instance
        """
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

    def _detect_provider(self, base_url: str) -> str:
        """Auto-detect provider from base URL"""
        url_lower = base_url.lower()
        if "openai.com" in url_lower:
            return "openai"
        elif "deepseek.com" in url_lower:
            return "deepseek"
        elif "dashscope.aliyuncs.com" in url_lower or "aliyun" in url_lower:
            return "qwen"
        elif "volces.com" in url_lower or "bytedance" in url_lower:
            return "doubao"
        elif "x.ai" in url_lower:
            return "xai"
        elif "generativelanguage.googleapis.com" in url_lower or "gemini" in url_lower:
            return "gemini"
        elif "moonshot.cn" in url_lower or "kimi" in url_lower:
            return "kimi"
        elif "localhost" in url_lower or "127.0.0.1" in url_lower:
            return "lm_studio"
        return "unknown"

    @staticmethod
    def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
        """Normalize vector rows to unit length"""
        if vectors.size == 0:
            return vectors.astype(np.float32, copy=False)
        vectors = vectors.astype(np.float32, copy=False)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-12, None)
        return vectors / norms

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers with authentication"""
        headers = {"Content-Type": "application/json"}
        
        # Add API key based on provider
        if self.api_key:
            if self.provider == "gemini":
                # Gemini uses query parameter instead of header
                pass
            elif self.provider == "doubao":
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                # Standard OpenAI-style authentication
                headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Add extra headers
        headers.update(self.extra_headers)
        return headers

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send POST request and return JSON response"""
        url = f"{self.base_url}{path}"
        
        # Special handling for Gemini API key
        if self.provider == "gemini" and self.api_key:
            url = f"{url}?key={self.api_key}"

        logger.info("LLM request URL: %s", url)
        
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._build_headers()
        req = Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                err_body = ""
            raise UniversalLLMError(
                f"API request failed ({exc.code}) for {path}: {err_body or exc.reason}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise UniversalLLMError(
                f"API request failed for {path}: {exc}",
                status_code=None,
            ) from exc

        text = raw.decode("utf-8", errors="ignore").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception as exc:
            raise UniversalLLMError(
                f"API returned invalid JSON for {path}"
            ) from exc

    def _stream_post_json(self, path: str, payload: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Send POST request and stream JSON responses (SSE format)"""
        url = f"{self.base_url}{path}"
        
        # Special handling for Gemini API key
        if self.provider == "gemini" and self.api_key:
            url = f"{url}?key={self.api_key}"

        logger.info("LLM stream request URL: %s", url)
        
        headers = self._build_headers()
        try:
            with requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.timeout,
            ) as resp:
                if resp.status_code >= 400:
                    err_body = (resp.text or "").strip()
                    raise UniversalLLMError(
                        f"API request failed ({resp.status_code}) for {path}: {err_body or resp.reason}",
                        status_code=resp.status_code,
                    )

                seen_stream_line = False
                for raw_line in resp.iter_lines(decode_unicode=True):
                    line = str(raw_line or "").strip()
                    if not line or line.startswith(":"):
                        continue
                    seen_stream_line = True
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
                        raise UniversalLLMError(
                            f"API returned invalid streaming JSON for {path}: {payload_text[:200]}"
                        ) from exc

                if not seen_stream_line:
                    text = (resp.text or "").strip()
                    if text:
                        try:
                            yield json.loads(text)
                        except Exception:
                            pass
        except requests.RequestException as exc:
            raise UniversalLLMError(
                f"API request failed for {path}: {exc}",
                status_code=None,
            ) from exc

    @staticmethod
    def _content_to_text(content: Any) -> str:
        """Extract text from various content formats"""
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
        """Extract text from chat completion response"""
        choices = resp.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        
        # Try message.content (standard format)
        message = first.get("message")
        if isinstance(message, dict):
            for key in ("content", "reasoning_content", "reasoning", "text"):
                text = self._content_to_text(message.get(key))
                if text:
                    return text
            text_raw = message.get("text")
            if isinstance(text_raw, str) and text_raw:
                return text_raw
        
        # Try direct text field
        text = first.get("text")
        if isinstance(text, str):
            return text
        
        return ""

    def _extract_stream_text(self, chunk: Dict[str, Any]) -> str:
        """Extract text from streaming chunk"""
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        
        # Try delta.content (streaming format)
        delta = first.get("delta")
        if isinstance(delta, dict):
            for key in ("content", "reasoning_content", "reasoning", "text"):
                text = self._content_to_text(delta.get(key))
                if text:
                    return text
            text_raw = delta.get("text")
            if isinstance(text_raw, str) and text_raw:
                return text_raw
        
        # Try message.content (some providers)
        message = first.get("message")
        if isinstance(message, dict):
            for key in ("content", "reasoning_content", "reasoning", "text"):
                text = self._content_to_text(message.get(key))
                if text:
                    return text
            text_raw = message.get("text")
            if isinstance(text_raw, str) and text_raw:
                return text_raw
        
        # Try direct text field
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
        """Build chat completion request payload"""
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
        """
        Send chat completion request (non-streaming)
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name/ID
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **extra: Additional parameters
        
        Returns:
            Generated text response
        """
        payload = self._build_chat_payload(
            messages=messages,
            model=model,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
        resp = self._post("/v1/chat/completions", payload)
        if isinstance(resp, dict) and isinstance(resp.get("error"), dict):
            err = resp.get("error") or {}
            message = str(err.get("message") or err.get("type") or "unknown provider error")
            raise UniversalLLMError(f"Chat request failed: {message}")
        text = self._extract_chat_text(resp)
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
        """
        Send chat completion request (streaming)
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name/ID
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **extra: Additional parameters
        
        Yields:
            Text chunks as they arrive
        """
        payload = self._build_chat_payload(
            messages=messages,
            model=model,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
        yielded = False
        chunk_count = 0
        first_chunk_preview = ""
        for chunk in self._stream_post_json("/v1/chat/completions", payload):
            chunk_count += 1
            if chunk_count == 1:
                try:
                    if isinstance(chunk, dict):
                        first_chunk_preview = f"keys={sorted(list(chunk.keys()))}"
                    else:
                        first_chunk_preview = f"type={type(chunk).__name__}"
                except Exception:
                    first_chunk_preview = "unavailable"
            if isinstance(chunk, dict) and isinstance(chunk.get("error"), dict):
                err = chunk.get("error") or {}
                message = str(err.get("message") or err.get("type") or "unknown provider error")
                logger.error(
                    "Upstream stream error chunk: provider=%s model=%s message=%s error=%s",
                    self.provider,
                    model,
                    message,
                    err,
                )
                raise UniversalLLMError(f"Chat stream failed: {message}")
            text = self._extract_stream_text(chunk)
            if text:
                yielded = True
                yield text
        if not yielded:
            logger.error(
                "Upstream stream produced no text: provider=%s model=%s chunk_count=%d first_chunk=%s",
                self.provider,
                model,
                chunk_count,
                first_chunk_preview,
            )
            # Fallback: some providers/models may close stream without text chunks.
            # Try one non-stream request so callers can still receive an answer.
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
        """
        Generate embeddings for texts
        
        Args:
            texts: List of text strings to embed
            model: Embedding model name
        
        Returns:
            Normalized embedding vectors as numpy array
        """
        payload = {"model": model, "input": list(texts)}
        resp = self._post("/v1/embeddings", payload)
        data = resp.get("data", [])
        if not isinstance(data, list):
            raise UniversalLLMError("Embeddings response missing data")
        
        # Sort by index if available
        try:
            data = sorted(data, key=lambda d: d.get("index", 0))
        except Exception:
            pass
        
        vectors = [item.get("embedding", []) for item in data]
        if len(vectors) != len(texts):
            raise UniversalLLMError("Embeddings count mismatch")
        
        vecs = np.asarray(vectors, dtype=np.float32)
        return self._normalize_rows(vecs)

    def _parse_rerank_response(self, resp: Dict[str, Any], expected: int) -> List[float]:
        """Parse reranking response in various formats"""
        # Try results field (common format)
        if isinstance(resp, dict) and "results" in resp:
            items = resp["results"]
        # Try data field (OpenAI-style)
        elif isinstance(resp, dict) and "data" in resp:
            items = resp["data"]
        # Try scores field (simple format)
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
            if found_scores:
                fill_value = min(found_scores) - 1.0
            else:
                fill_value = 0.0
            scores = [s if s is not None else fill_value for s in scores]
            return [float(x) for x in scores]

        # Sequential format without index
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

    def rerank_scores(
        self, query: str, docs: Sequence[str], model: str
    ) -> List[float] | None:
        """
        Rerank documents by relevance to query
        
        Args:
            query: Query text
            docs: List of document texts to rerank
            model: Reranking model name
        
        Returns:
            List of relevance scores, or None if reranking not supported
        """
        payload = {
            "model": model,
            "query": query,
            "documents": list(docs),
            "top_n": len(docs),
            "return_documents": False,
        }
        try:
            resp = self._post("/v1/rerank", payload)
        except UniversalLLMError as exc:
            if exc.status_code in {400, 404}:
                self.rerank_supported = False
                return None
            raise
        
        self.rerank_supported = True
        return self._parse_rerank_response(resp, expected=len(docs))


# Backward compatibility alias
LmStudioClient = UniversalLLMClient
LmStudioRequestError = UniversalLLMError
