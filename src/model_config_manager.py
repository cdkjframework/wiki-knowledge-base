"""
Model Configuration Management API
Provides REST API endpoints for managing AI model provider configurations
"""
import json
import logging
from typing import Any, Dict, List, Optional

try:
    from .store.db.connection import DatabaseConnection
    from .store.db.model_config_store import ModelConfigStore
    from .universal_llm_client import UniversalLLMClient, UniversalLLMError
except ImportError:  # pragma: no cover
    from store.db.connection import DatabaseConnection
    from store.db.model_config_store import ModelConfigStore
    from universal_llm_client import UniversalLLMClient, UniversalLLMError

logger = logging.getLogger(__name__)

_VALID_MODEL_TYPES = frozenset({"chat", "embedding", "rerank"})

# 进程内 HF 本地加载（不走 OpenAI SDK）
LOCAL_HF_PROVIDER = "huggingface"
LOCAL_HF_BASE_URL = "local://huggingface"
LOCAL_HF_ALIASES = frozenset({"huggingface", "hf", "local_hf", "local"})


def normalize_model_type(raw: Any, *, default: str = "chat") -> str:
    """统一 model_type：embedding / rerank / chat（知识库分析）。"""
    text = str(raw or default).strip().lower()
    if text in {"embed", "embedding"}:
        return "embedding"
    if text in {"rerank", "reranker"}:
        return "rerank"
    if text in {"chat", "analysis", "llm", "completion"}:
        return "chat"
    if text in _VALID_MODEL_TYPES:
        return text
    return default


def is_local_hf_provider(provider: Any) -> bool:
    return str(provider or "").strip().lower() in LOCAL_HF_ALIASES


def normalize_base_url_for_provider(provider: str, base_url: str | None) -> str:
    """huggingface 允许空 base_url，落库为 local://huggingface。"""
    if is_local_hf_provider(provider):
        text = str(base_url or "").strip()
        return text or LOCAL_HF_BASE_URL
    return str(base_url or "").strip()


class ModelConfigManager:
    """Manager for AI model configurations with database storage"""
    
    def __init__(self, db_connection: DatabaseConnection):
        self.store = ModelConfigStore(db_connection)
        self._client_cache: Dict[int, UniversalLLMClient] = {}
    
    def add_model_config(
        self,
        name: str,
        provider: str,
        base_url: str,
        model_name: str,
        api_key: Optional[str] = None,
        model_type: str = "chat",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 30.0,
        extra_headers: Optional[Dict[str, str]] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
        is_default: bool = False,
        description: Optional[str] = None,
        dimension: Optional[int] = None,
        max_input_length: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Add a new model configuration
        
        Returns:
            Dict with added config details
        """
        try:
            config_id = self.store.add_config(
                name=name,
                provider=provider,
                base_url=normalize_base_url_for_provider(provider, base_url),
                model_name=model_name,
                api_key=api_key,
                model_type=normalize_model_type(model_type),
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                extra_headers=extra_headers,
                extra_params=extra_params,
                is_active=is_active,
                is_default=is_default,
                description=description,
                dimension=dimension,
                max_input_length=max_input_length,
            )
            config = self.store.get_config(config_id)
            return {"ok": True, "config": self._sanitize_config(config)}
        except Exception as exc:
            logger.error(f"Failed to add model config: {exc}")
            return {"ok": False, "error": str(exc)}
    
    def update_model_config(self, config_id: int, **kwargs: Any) -> Dict[str, Any]:
        """
        Update an existing model configuration
        
        Returns:
            Dict with update status
        """
        try:
            # Clear cache for this config
            if config_id in self._client_cache:
                del self._client_cache[config_id]

            if "model_type" in kwargs and kwargs["model_type"] is not None:
                kwargs["model_type"] = normalize_model_type(kwargs["model_type"])
            if "provider" in kwargs or "base_url" in kwargs:
                provider = kwargs.get("provider")
                if provider is None:
                    existing = self.store.get_config(config_id) or {}
                    provider = existing.get("provider")
                if "base_url" in kwargs or is_local_hf_provider(provider):
                    kwargs["base_url"] = normalize_base_url_for_provider(
                        str(provider or ""),
                        kwargs.get("base_url"),
                    )
            success = self.store.update_config(config_id, **kwargs)
            if not success:
                return {"ok": False, "error": "Config not found or no changes made"}
            
            config = self.store.get_config(config_id)
            return {"ok": True, "config": self._sanitize_config(config)}
        except Exception as exc:
            logger.error(f"Failed to update model config: {exc}")
            return {"ok": False, "error": str(exc)}
    
    def delete_model_config(self, config_id: int) -> Dict[str, Any]:
        """
        Delete a model configuration
        
        Returns:
            Dict with deletion status
        """
        try:
            # Clear cache
            if config_id in self._client_cache:
                del self._client_cache[config_id]
            
            success = self.store.delete_config(config_id)
            if not success:
                return {"ok": False, "error": "Config not found"}
            
            return {"ok": True, "deleted": config_id}
        except Exception as exc:
            logger.error(f"Failed to delete model config: {exc}")
            return {"ok": False, "error": str(exc)}
    
    def get_model_config(
        self, 
        config_id: Optional[int] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a specific model configuration by ID or name
        
        Returns:
            Dict with config details or error
        """
        try:
            if config_id is not None:
                config = self.store.get_config(config_id)
            elif name is not None:
                config = self.store.get_config_by_name(name)
            else:
                return {"ok": False, "error": "Must provide config_id or name"}
            
            if not config:
                return {"ok": False, "error": "Config not found"}
            
            return {"ok": True, "config": self._sanitize_config(config)}
        except Exception as exc:
            logger.error(f"Failed to get model config: {exc}")
            return {"ok": False, "error": str(exc)}
    
    def list_model_configs(
        self,
        provider: Optional[str] = None,
        is_active: Optional[bool] = None,
        model_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List model configurations with optional filters
        
        Returns:
            Dict with list of configs
        """
        try:
            mt = normalize_model_type(model_type) if model_type else None
            configs = self.store.list_configs(
                provider=provider,
                is_active=is_active,
                model_type=mt,
            )
            sanitized = [self._sanitize_config(cfg) for cfg in configs]
            return {"ok": True, "configs": sanitized, "count": len(sanitized)}
        except Exception as exc:
            logger.error(f"Failed to list model configs: {exc}")
            return {"ok": False, "error": str(exc), "configs": [], "count": 0}    
    def get_default_config(self, model_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the default model configuration
        
        Returns:
            Dict with default config or error
        """
        try:
            mt = normalize_model_type(model_type) if model_type else None
            config = self.store.get_default_config(model_type=mt)
            if not config:
                return {"ok": False, "error": "No default config set"}
            
            return {"ok": True, "config": self._sanitize_config(config)}
        except Exception as exc:
            logger.error(f"Failed to get default config: {exc}")
            return {"ok": False, "error": str(exc)}
    
    def set_default_config(self, config_id: int) -> Dict[str, Any]:
        """
        Set a configuration as default
        
        Returns:
            Dict with status
        """
        try:
            success = self.store.set_default(config_id)
            if not success:
                return {"ok": False, "error": "Config not found"}
            config = self.store.get_config(config_id)
            return {
                "ok": True,
                "default_config_id": config_id,
                "config": self._sanitize_config(config),
            }
        except Exception as exc:
            logger.error(f"Failed to set default config: {exc}")
            return {"ok": False, "error": str(exc)}
    
    def get_client(
        self,
        config_id: Optional[int] = None,
        name: Optional[str] = None,
        use_default: bool = False,
    ) -> UniversalLLMClient:
        """
        Get an LLM client instance based on configuration
        
        Args:
            config_id: Config ID to use
            name: Config name to use
            use_default: Use default config if True
        
        Returns:
            UniversalLLMClient instance
        
        Raises:
            ValueError: If config not found or invalid
        """
        # Get config
        if use_default:
            config = self.store.get_default_config(model_type="chat")
            if not config:
                raise ValueError("No default model config set")
        elif config_id is not None:
            # Check cache
            if config_id in self._client_cache:
                return self._client_cache[config_id]
            
            config = self.store.get_config(config_id)
            if not config:
                raise ValueError(f"Model config {config_id} not found")
        elif name is not None:
            config = self.store.get_config_by_name(name)
            if not config:
                raise ValueError(f"Model config '{name}' not found")
        else:
            raise ValueError("Must provide config_id, name, or use_default=True")
        
        if not config.get("is_active"):
            raise ValueError(f"Model config '{config['name']}' is not active")
        
        # Create client
        client = UniversalLLMClient(
            base_url=config["base_url"],
            api_key=config.get("api_key"),
            timeout=config.get("timeout", 30.0),
            provider=config["provider"],
            extra_headers=config.get("extra_headers") or {},
        )
        
        # Cache if we have an ID
        if config_id is not None:
            self._client_cache[config_id] = client
        
        return client
    
    def test_config(
        self,
        config_id: Optional[int] = None,
        name: Optional[str] = None,
        config_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Test a model configuration by sending a simple request
        
        Args:
            config_id: Test existing config by ID
            name: Test existing config by name
            config_data: Test temporary config without saving
        
        Returns:
            Dict with test results
        """
        try:
            if config_data:
                provider = str(config_data.get("provider") or "unknown")
                model_name = config_data["model_name"]
                model_type = normalize_model_type(config_data.get("model_type"), default="chat")
                if is_local_hf_provider(provider):
                    return {
                        "ok": True,
                        "status": "success",
                        "message": f"本地 HF 配置有效：{model_name}（设为默认后由进程加载）",
                        "provider": LOCAL_HF_PROVIDER,
                        "model_type": model_type,
                    }
                client = UniversalLLMClient(
                    base_url=config_data["base_url"],
                    api_key=config_data.get("api_key"),
                    timeout=config_data.get("timeout", 30.0),
                    provider=provider,
                    extra_headers=config_data.get("extra_headers") or {},
                )
            else:
                if config_id is not None:
                    config = self.store.get_config(config_id)
                else:
                    config = self.store.get_config_by_name(name)
                if not config:
                    return {"ok": False, "status": "error", "error": "Config not found"}
                provider = str(config.get("provider") or "unknown")
                model_name = config["model_name"]
                model_type = normalize_model_type(config.get("model_type"), default="chat")
                if is_local_hf_provider(provider):
                    return {
                        "ok": True,
                        "status": "success",
                        "message": f"本地 HF 配置有效：{model_name}（设为默认后由进程加载）",
                        "provider": LOCAL_HF_PROVIDER,
                        "model_type": model_type,
                    }
                client = self.get_client(config_id=config_id, name=name)

            if model_type == "embedding":
                vectors = client.embed_texts(["ping"], model=model_name)
                dim = int(getattr(vectors, "shape", [0, 0])[1]) if vectors is not None else 0
                return {
                    "ok": True,
                    "status": "success",
                    "message": f"Embedding 连通正常，维度={dim or '—'}",
                    "provider": client.provider,
                    "dimension": dim or None,
                }
            if model_type == "rerank":
                scores = client.rerank_scores(
                    query="ping",
                    docs=["pong"],
                    model=model_name,
                )
                return {
                    "ok": True,
                    "status": "success",
                    "message": f"Rerank 连通正常（scores={len(scores) if scores is not None else 0}）",
                    "provider": client.provider,
                }

            response = client.chat_once(
                messages=[{"role": "user", "content": "Hello"}],
                model=model_name,
                max_tokens=50,
            )
            
            return {
                "ok": True,
                "status": "success",
                "response": response[:200] if response else "",
                "provider": client.provider,
            }
        except UniversalLLMError as exc:
            logger.error(f"Model config test failed: {exc}")
            return {
                "ok": False,
                "status": "error",
                "error": str(exc),
                "status_code": getattr(exc, "status_code", None),
            }
        except Exception as exc:
            logger.error(f"Model config test failed: {exc}")
            return {"ok": False, "status": "error", "error": str(exc)}

    def list_remote_models(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        config_id: Optional[int] = None,
        extra_headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """按当前表单（或已存配置的密钥）去上游拉模型列表。"""
        try:
            provider_name = str(provider or "").strip()
            if is_local_hf_provider(provider_name):
                return {"ok": False, "error": "本地 HuggingFace 加载不支持远程获取模型"}
            url = normalize_base_url_for_provider(provider_name, base_url)
            if not url:
                return {"ok": False, "error": "缺少接口地址 base_url"}
            key = (api_key or "").strip() or None
            headers = dict(extra_headers or {})
            if config_id is not None and not key:
                stored = self.store.get_config(int(config_id)) or {}
                key = (stored.get("api_key") or "").strip() or None
                if not headers and stored.get("extra_headers"):
                    headers = dict(stored.get("extra_headers") or {})
            client = UniversalLLMClient(
                base_url=url,
                api_key=key,
                timeout=float(timeout or 30.0),
                provider=provider_name or None,
                extra_headers=headers,
            )
            models = client.list_models()
            return {
                "ok": True,
                "models": [{"id": m, "label": m} for m in models],
                "count": len(models),
                "provider": client.provider,
            }
        except UniversalLLMError as exc:
            logger.error(f"List remote models failed: {exc}")
            return {
                "ok": False,
                "error": str(exc),
                "status_code": getattr(exc, "status_code", None),
            }
        except Exception as exc:
            logger.error(f"List remote models failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def get_supported_providers(self) -> Dict[str, Any]:
        """
        Get list of supported AI providers
        
        Returns:
            Dict with provider information
        """
        # 本地 OpenAI 兼容 / 进程内 HF 一般不强制 api_key
        no_key_required = {"lm_studio", "ollama", LOCAL_HF_PROVIDER, "hf", "local_hf"}
        providers: List[Dict[str, Any]] = [
            {
                "name": LOCAL_HF_PROVIDER,
                "base_url": LOCAL_HF_BASE_URL,
                "requires_api_key": False,
                "local_load": True,
                "model_types": ["embedding", "rerank"],
                "label": "HuggingFace 本地加载",
            }
        ]
        # Embedding/Rerank 仅展示能接 Qwen3 系的接入商；其余只给 chat
        retrieval_providers = {"lm_studio", "qwen", "dashscope"}
        chat_only = {
            "ollama",
            "openai",
            "deepseek",
            "kimi",
            "moonshot",
            "doubao",
            "xai",
            "gemini",
        }
        for provider, base_url in UniversalLLMClient.PROVIDER_ENDPOINTS.items():
            if provider in retrieval_providers:
                model_types = ["chat", "embedding", "rerank"]
            elif provider in chat_only:
                model_types = ["chat"]
            else:
                model_types = ["chat"]
            providers.append({
                "name": provider,
                "base_url": base_url,
                "requires_api_key": provider not in no_key_required,
                "local_load": False,
                "model_types": model_types,
            })
        
        return {"ok": True, "providers": providers}

    def bootstrap_default_configs(self) -> Dict[str, Any]:
        """Seed built-in provider configs if they do not exist（三类：chat / embedding / rerank）。"""
        presets = [
            # —— 知识库分析（chat）——
            {
                "name": "local-lm-studio",
                "provider": "lm_studio",
                "base_url": "http://127.0.0.1:1234",
                "model_name": "local-model",
                "model_type": "chat",
                "timeout": 180.0,
                "description": "本地分析模型（LM Studio / OpenAI compatible）",
                "is_default": True,
            },
            {
                "name": "local-ollama",
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434/v1",
                "model_name": "qwen2.5:7b",
                "model_type": "chat",
                "timeout": 180.0,
                "description": "本地分析模型（Ollama OpenAI compatible，无需 api_key）",
            },
            {
                "name": "openai-default",
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o-mini",
                "model_type": "chat",
                "description": "OpenAI 分析模型（需填写 api_key）",
            },
            {
                "name": "deepseek-default",
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "model_name": "deepseek-chat",
                "model_type": "chat",
                "description": "DeepSeek 分析模型（需填写 api_key）",
            },
            {
                "name": "qwen-default",
                "provider": "qwen",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model_name": "qwen-plus",
                "model_type": "chat",
                "description": "通义千问分析模型（国内普通接口；Team 请改业务空间域名）",
            },
            {
                "name": "doubao-default",
                "provider": "doubao",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model_name": "doubao-pro-32k",
                "model_type": "chat",
                "description": "豆包分析模型（需填写 api_key）",
            },
            {
                "name": "xai-default",
                "provider": "xai",
                "base_url": "https://api.x.ai/v1",
                "model_name": "grok-beta",
                "model_type": "chat",
                "description": "xAI 分析模型（需填写 api_key）",
            },
            {
                "name": "gemini-default",
                "provider": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "model_name": "gemini-pro",
                "model_type": "chat",
                "description": "Gemini 分析模型（需填写 api_key）",
            },
            {
                "name": "kimi-default",
                "provider": "kimi",
                "base_url": "https://api.moonshot.cn/v1",
                "model_name": "moonshot-v1-8k",
                "model_type": "chat",
                "description": "Kimi 分析模型（需填写 api_key）",
            },
            # —— Embedding ——
            {
                "name": "local-hf-embedding",
                "provider": LOCAL_HF_PROVIDER,
                "base_url": LOCAL_HF_BASE_URL,
                "model_name": "Qwen/Qwen3-Embedding-0.6B",
                "model_type": "embedding",
                "description": "进程内 HF 本地 Embedding（从 models/hf_cache 加载；设为默认即生效）",
                "is_default": True,
                "max_input_length": 8192,
            },
            {
                "name": "openai-embedding",
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model_name": "text-embedding-3-large",
                "model_type": "embedding",
                "description": "OpenAI Embedding（需填写 api_key）；维度以服务商为准",
                "max_tokens": 8192,
                "max_input_length": 8192,
                "dimension": 3072,
            },
            {
                "name": "local-embedding-openai-compat",
                "provider": "lm_studio",
                "base_url": "http://127.0.0.1:1234",
                "model_name": "text-embedding-local",
                "model_type": "embedding",
                "description": "本地 OpenAI 兼容 Embedding（LM Studio 等）",
                "max_input_length": 8192,
            },
            # —— Reranker ——
            {
                "name": "local-hf-rerank",
                "provider": LOCAL_HF_PROVIDER,
                "base_url": LOCAL_HF_BASE_URL,
                "model_name": "Qwen/Qwen3-Reranker-0.6B",
                "model_type": "rerank",
                "description": "进程内 HF 本地 Reranker（从 models/hf_cache 加载；设为默认即生效）",
                "is_default": True,
                "max_input_length": 512,
            },
            {
                "name": "openai-compat-rerank",
                "provider": "lm_studio",
                "base_url": "http://127.0.0.1:1234",
                "model_name": "rerank-local",
                "model_type": "rerank",
                "description": "本地 OpenAI 兼容 Rerank 端点（若网关提供 /rerank）",
                "max_input_length": 512,
            },
            {
                "name": "cohere-style-rerank-placeholder",
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model_name": "rerank-placeholder",
                "model_type": "rerank",
                "description": "占位：可改为实际 Rerank 服务商地址与模型名",
                "max_input_length": 512,
            },
        ]

        created: List[str] = []
        skipped: List[str] = []
        for item in presets:
            name = item["name"]
            exists = self.store.get_config_by_name(name)
            if exists:
                skipped.append(name)
                continue
            result = self.add_model_config(
                name=name,
                provider=item["provider"],
                base_url=item["base_url"],
                model_name=item["model_name"],
                api_key=None,
                model_type=str(item.get("model_type") or "chat"),
                temperature=0.2 if normalize_model_type(item.get("model_type")) == "chat" else 0.0,
                max_tokens=item.get("max_tokens"),
                timeout=float(item.get("timeout") or 60.0),
                is_active=True,
                is_default=bool(item.get("is_default", False)),
                description=item.get("description"),
                dimension=item.get("dimension"),
                max_input_length=item.get("max_input_length") or item.get("max_tokens"),
            )
            if result.get("ok"):
                created.append(name)
            else:
                skipped.append(name)

        return {
            "ok": True,
            "created": created,
            "skipped": skipped,
            "count_created": len(created),
            "count_skipped": len(skipped),
            "message": (
                f"初始化完成：新建 {len(created)}，跳过 {len(skipped)}。"
                "Embedding/Rerank 可选 HuggingFace 本地加载；设为默认会应用到当前进程运行时。"
            ),
        }
    
    @staticmethod
    def _sanitize_config(config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Remove sensitive information from config for API response"""
        if not config:
            return None
        
        sanitized = config.copy()
        # Mask API key
        if sanitized.get("api_key"):
            key = sanitized["api_key"]
            if len(key) > 8:
                sanitized["api_key"] = key[:4] + "****" + key[-4:]
            else:
                sanitized["api_key"] = "****"
        
        return sanitized
