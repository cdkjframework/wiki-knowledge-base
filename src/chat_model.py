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
        # Do not set process-wide offline env flags here.
        # ChatModel uses local_files_only per from_pretrained call, so global flags
        # would incorrectly force other modules (e.g. embedding/reranker fallback)
        # to stay offline and block auto-download.
        return

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

    @staticmethod
    def _summarize_text(text: str, limit: int = 120) -> str:
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    @staticmethod
    def _preview_text(text: str, limit: int = 300) -> str:
        if not text:
            return ""
        cleaned = str(text).replace("\r", "\\r").replace("\n", "\\n")
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit] + "..."

    def _summarize_messages(self, messages: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        count = len(messages)
        last_role = ""
        last_len = 0
        last_preview = ""
        if messages:
            last = messages[-1]
            last_role = str(last.get("role", "")).strip().lower()
            content_text = self._msg_content_to_text(last.get("content", ""))
            last_len = len(content_text)
            last_preview = self._summarize_text(content_text)
        return {
            "count": count,
            "last_role": last_role,
            "last_len": last_len,
            "last_preview": last_preview,
        }

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
        summary = self._summarize_messages(messages)
        logger.info(
            "Chat input: model=%s temp=%s max_tokens=%s messages=%s last_role=%s last_len=%s last_preview=%s",
            model,
            temperature,
            max_tokens,
            summary["count"],
            summary["last_role"],
            summary["last_len"],
            summary["last_preview"],
        )
        if self.use_lm_studio and self._lm_client is not None:
            logger.info("Chat inference via LM Studio: model=%s", model)
            result = self._lm_client.chat_once(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.info("Chat output: model=%s chars=%s", model, len(result))
            logger.info("Chat output preview: model=%s preview=%s", model, self._preview_text(result))
            return result
        logger.info("Chat inference via local model: model=%s", model)
        result = self._local_chat_once(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.info("Chat output: model=%s chars=%s", model, len(result))
        logger.info("Chat output preview: model=%s preview=%s", model, self._preview_text(result))
        return result

    def chat_stream(
        self,
        messages: Sequence[Dict[str, Any]],
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Sequence[str]:
        summary = self._summarize_messages(messages)
        logger.info(
            "Chat stream input: model=%s temp=%s max_tokens=%s messages=%s last_role=%s last_len=%s last_preview=%s",
            model,
            temperature,
            max_tokens,
            summary["count"],
            summary["last_role"],
            summary["last_len"],
            summary["last_preview"],
        )
        if self.use_lm_studio and self._lm_client is not None:
            logger.info("Chat stream via LM Studio: model=%s", model)
            def _logged_stream() -> Sequence[str]:
                total = 0
                chunks = 0
                preview_parts: List[str] = []
                preview_len = 0
                preview_limit = 300
                for piece in self._lm_client.chat_stream(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    text = str(piece or "")
                    if text:
                        total += len(text)
                        chunks += 1
                        if preview_len < preview_limit:
                            remain = preview_limit - preview_len
                            snippet = text[:remain]
                            if snippet:
                                preview_parts.append(snippet)
                                preview_len += len(snippet)
                    yield piece
                preview = "".join(preview_parts)
                logger.info(
                    "Chat stream output: model=%s chunks=%s chars=%s preview=%s",
                    model,
                    chunks,
                    total,
                    self._preview_text(preview),
                )

            return _logged_stream()
        logger.info("Chat stream via local model: model=%s", model)
        text = self._local_chat_once(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.info(
            "Chat stream output: model=%s chunks=1 chars=%s preview=%s",
            model,
            len(text),
            self._preview_text(text),
        )
        return [text]
