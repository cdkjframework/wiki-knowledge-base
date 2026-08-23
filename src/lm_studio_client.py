"""LM Studio Client compatibility wrapper."""

try:
    from .universal_llm_client import UniversalLLMClient, UniversalLLMError
except ImportError:  # pragma: no cover
    from universal_llm_client import UniversalLLMClient, UniversalLLMError


LmStudioRequestError = UniversalLLMError


class LmStudioClient(UniversalLLMClient):
    """Backward-compatible LM Studio client backed by UniversalLLMClient."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30):
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            provider="lm_studio",
        )


__all__ = ["LmStudioClient", "LmStudioRequestError", "UniversalLLMClient", "UniversalLLMError"]