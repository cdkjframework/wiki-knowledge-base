import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Sequence

import torch

try:
    from .lm_studio_client import LmStudioClient
except ImportError:  # pragma: no cover
    from lm_studio_client import LmStudioClient

logger = logging.getLogger(__name__)


class ChatModel:
    def __init__(
        self,
        device: str,
        model_cache_dir: str | Path,
        use_lm_studio: bool = True,
        lm_client: LmStudioClient | None = None,
        lm_base_url: str | None = None,
        lm_api_key: str | None = None,
        lm_timeout: float = 30.0,
        local_files_only: bool = True,
        default_temperature: float = 0.2,
        default_max_tokens: int = 512,
    ):
        self.device = str(device)
        self.model_cache_dir = Path(model_cache_dir)
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_lm_studio = bool(use_lm_studio)
        self.local_files_only = bool(local_files_only)
        self._configure_hf_offline_mode()
        self.default_temperature = float(default_temperature)
        self.default_max_tokens = max(1, int(default_max_tokens))

        self._lm_client = lm_client
        if self._lm_client is None:
            base = (lm_base_url or "").strip()
            if base:
                self._lm_client = LmStudioClient(
                    base,
                    api_key=(lm_api_key or "").strip() or None,
                    timeout=float(lm_timeout),
                )

        self._tokenizer = None
        self._model = None
        self._loaded_model_name: str | None = None
        logger.info(
            "ChatModel initialized: use_lm_studio=%s local_files_only=%s cache_dir=%s",
            self.use_lm_studio,
            self.local_files_only,
            self.model_cache_dir,
        )

    def _configure_hf_offline_mode(self) -> None:
        if not self.local_files_only:
            return
        # Avoid remote metadata checks in local cache mode.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    @staticmethod
    def _msg_content_to_text(content: Any) -> str:
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
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
            return "".join(parts)
        return ""

    def _messages_to_prompt(self, messages: Sequence[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for msg in messages:
            role = str(msg.get("role", "user")).strip().lower() or "user"
            content = self._msg_content_to_text(msg.get("content", ""))
            if not content:
                continue
            lines.append(f"{role}: {content}")
        lines.append("assistant:")
        return "\n".join(lines)

    def _ensure_local_model(self, model_name: str) -> None:
        if (
            self._model is not None
            and self._tokenizer is not None
            and self._loaded_model_name == model_name
        ):
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as exc:
            raise RuntimeError(
                "Failed to import transformers stack for local chat model."
            ) from exc

        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True,
            local_files_only=self.local_files_only,
            cache_dir=str(self.model_cache_dir),
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            local_files_only=self.local_files_only,
            cache_dir=str(self.model_cache_dir),
        )
        self._model.to(self.device)
        self._model.eval()
        self._loaded_model_name = model_name
        logger.info("Local chat model loaded: %s", model_name)

    def _local_chat_once(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        self._ensure_local_model(model)
        assert self._tokenizer is not None
        assert self._model is not None

        tokenized = None
        if hasattr(self._tokenizer, "apply_chat_template"):
            try:
                tokenized = self._tokenizer.apply_chat_template(
                    list(messages),
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt",
                )
            except Exception:
                tokenized = None
        if tokenized is None:
            prompt = self._messages_to_prompt(messages)
            tokenized = self._tokenizer(prompt, return_tensors="pt")

        if isinstance(tokenized, dict):
            input_ids = tokenized["input_ids"]
            attention_mask = tokenized.get("attention_mask")
        else:
            input_ids = tokenized
            attention_mask = None

        input_ids = input_ids.to(self.device)
        if attention_mask is not None:
            attention_mask = attention_mask.to(self.device)

        temp = self.default_temperature if temperature is None else float(temperature)
        max_new = self.default_max_tokens if max_tokens is None else int(max_tokens)
        do_sample = temp > 1e-8
        pad_id = self._tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self._tokenizer.eos_token_id

        gen_kwargs: Dict[str, Any] = {
            "max_new_tokens": max(1, max_new),
            "do_sample": do_sample,
            "pad_token_id": pad_id,
        }
        if do_sample:
            gen_kwargs["temperature"] = temp

        with torch.no_grad():
            output = self._model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                **gen_kwargs,
            )
        generated = output[:, input_ids.shape[1] :]
        return self._tokenizer.decode(generated[0], skip_special_tokens=True).strip()

    def chat_once(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if self.use_lm_studio and self._lm_client is not None:
            logger.info("Chat inference via LM Studio: model=%s", model)
            return self._lm_client.chat_once(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        logger.info("Chat inference via local model: model=%s", model)
        return self._local_chat_once(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
