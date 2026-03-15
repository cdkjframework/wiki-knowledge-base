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
                base_url=base_url,
                model_name=model_name,
                api_key=api_key,
                model_type=model_type,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                extra_headers=extra_headers,
                extra_params=extra_params,
                is_active=is_active,
                is_default=is_default,
                description=description,
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
            configs = self.store.list_configs(
                provider=provider,
                is_active=is_active,
                model_type=model_type,
            )
            sanitized = [self._sanitize_config(cfg) for cfg in configs]
            return {"ok": True, "configs": sanitized, "count": len(sanitized)}
        except Exception as exc:
            logger.error(f"Failed to list model configs: {exc}")
            return {"ok": False, "error": str(exc)}
    
    def get_default_config(self) -> Dict[str, Any]:
        """
        Get the default model configuration
        
        Returns:
            Dict with default config or error
        """
        try:
            config = self.store.get_default_config()
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
            
            return {"ok": True, "default_config_id": config_id}
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
            config = self.store.get_default_config()
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
                # Test temporary config
                client = UniversalLLMClient(
                    base_url=config_data["base_url"],
                    api_key=config_data.get("api_key"),
                    timeout=config_data.get("timeout", 30.0),
                    provider=config_data.get("provider", "unknown"),
                    extra_headers=config_data.get("extra_headers") or {},
                )
                model_name = config_data["model_name"]
            else:
                # Test existing config
                client = self.get_client(config_id=config_id, name=name)
                if config_id is not None:
                    config = self.store.get_config(config_id)
                else:
                    config = self.store.get_config_by_name(name)
                model_name = config["model_name"]
            
            # Send test message
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
    
    def get_supported_providers(self) -> Dict[str, Any]:
        """
        Get list of supported AI providers
        
        Returns:
            Dict with provider information
        """
        providers = []
        for provider, base_url in UniversalLLMClient.PROVIDER_ENDPOINTS.items():
            providers.append({
                "name": provider,
                "base_url": base_url,
                "requires_api_key": provider not in {"lm_studio"},
            })
        
        return {"ok": True, "providers": providers}

    def bootstrap_default_configs(self) -> Dict[str, Any]:
        """Seed built-in provider configs if they do not exist."""
        presets = [
            {
                "name": "local-lm-studio",
                "provider": "lm_studio",
                "base_url": "http://127.0.0.1:1234",
                "model_name": "local-model",
                "description": "本地模型（LM Studio/OpenAI compatible）",
                "is_default": True,
            },
            {
                "name": "openai-default",
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o-mini",
                "description": "OpenAI 默认配置（需填写 api_key）",
            },
            {
                "name": "deepseek-default",
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "model_name": "deepseek-chat",
                "description": "DeepSeek 默认配置（需填写 api_key）",
            },
            {
                "name": "qwen-default",
                "provider": "qwen",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model_name": "qwen-plus",
                "description": "Qwen 默认配置（需填写 api_key）",
            },
            {
                "name": "doubao-default",
                "provider": "doubao",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "model_name": "doubao-pro-32k",
                "description": "豆包默认配置（需填写 api_key）",
            },
            {
                "name": "xai-default",
                "provider": "xai",
                "base_url": "https://api.x.ai/v1",
                "model_name": "grok-beta",
                "description": "xAI 默认配置（需填写 api_key）",
            },
            {
                "name": "gemini-default",
                "provider": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "model_name": "gemini-pro",
                "description": "Gemini 默认配置（需填写 api_key）",
            },
            {
                "name": "kimi-default",
                "provider": "kimi",
                "base_url": "https://api.moonshot.cn/v1",
                "model_name": "moonshot-v1-8k",
                "description": "Kimi 默认配置（需填写 api_key）",
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
                model_type="chat",
                temperature=0.2,
                timeout=30.0,
                is_active=True,
                is_default=bool(item.get("is_default", False)),
                description=item.get("description"),
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
