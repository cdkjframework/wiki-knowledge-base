from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
import json
import logging
import mimetypes
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence
from urllib.parse import parse_qs, unquote, urlparse

try:
    from ..store.db.history_store import DatabaseHistoryStore
    from ..store.db.connection import DatabaseConnection
    from ..store.interfaces import HistoryStore, SessionIdStore
    from ..store.memory_store import InMemoryHistoryStore, InMemorySessionIdStore
    from ..store.redis.session_store import RedisSessionIdStore
    from ..model_config_manager import ModelConfigManager
    from ..mcp_local import MCP_DOC_PREFIX, McpConfigManager
    from ..shared.config_paths import load_project_config, resolve_config_path, resolve_project_root
    from .handlers import (
        handle_delete_history,
        handle_delete_kb,
        handle_delete_mcp,
        handle_delete_model,
        handle_delete_session,
        handle_get_history,
        handle_get_kb,
        handle_get_mcp,
        handle_get_model,
        handle_get_query,
        handle_get_session,
        handle_get_stats,
        handle_post_kb,
        handle_post_mcp,
        handle_post_model,
        handle_post_query,
        handle_post_session,
        handle_put_kb,
        handle_put_mcp,
        handle_put_model,
    )
    from .static_ui import (
        is_api_or_docs_path,
        legacy_web_enabled,
        resolve_frontend_dist,
        resolve_legacy_web_dir,
        should_spa_fallback,
    )
    from .api_prefix import strip_api_prefix
except ImportError:  # pragma: no cover
    from store.db.history_store import DatabaseHistoryStore
    from store.db.connection import DatabaseConnection
    from store.interfaces import HistoryStore, SessionIdStore
    from store.memory_store import InMemoryHistoryStore, InMemorySessionIdStore
    from store.redis.session_store import RedisSessionIdStore
    from model_config_manager import ModelConfigManager
    from mcp_local import MCP_DOC_PREFIX, McpConfigManager
    from shared.config_paths import load_project_config, resolve_config_path, resolve_project_root
    from api.handlers import (
        handle_delete_history,
        handle_delete_kb,
        handle_delete_mcp,
        handle_delete_model,
        handle_delete_session,
        handle_get_history,
        handle_get_kb,
        handle_get_mcp,
        handle_get_model,
        handle_get_query,
        handle_get_session,
        handle_get_stats,
        handle_post_kb,
        handle_post_mcp,
        handle_post_model,
        handle_post_query,
        handle_post_session,
        handle_put_kb,
        handle_put_mcp,
        handle_put_model,
    )
    from api.static_ui import (
        is_api_or_docs_path,
        legacy_web_enabled,
        resolve_frontend_dist,
        resolve_legacy_web_dir,
        should_spa_fallback,
    )
    from api.api_prefix import strip_api_prefix

try:
    from ..knowledge_base import KnowledgeBase
except ImportError:  # pragma: no cover
    from knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


PROJECT_ROOT = resolve_project_root()
FRONTEND_DIST = resolve_frontend_dist(PROJECT_ROOT)
LEGACY_WEB_DIR = resolve_legacy_web_dir(PROJECT_ROOT)
DOCS_DIR = PROJECT_ROOT / "docs"
ASSETS_DIR = PROJECT_ROOT / "assets"
CHAT_MCP_SOURCE_FILENAME = "__mcp_call__/runtime.md"

DEFAULT_SYSTEM_INTRO = """您的专属知识伙伴：WIKI本地知识系统

您好！当您询问“你是谁？”时，这是在了解本系统的核心身份。请参考以下全面介绍：

第一部分：关于“WIKI本地知识”是谁（系统定位）

直接回答“你是谁？”：我是WIKI本地知识，您的本地私有化知识库与智能助理。

核心定位：我本质上是为您服务的“第二大脑”和“专属知识引擎”。我的一切能力都基于您提供的知识，并在您的完全掌控下运行。

关键特性：我部署在您的本地环境中，确保所有数据的私有性与安全，不依赖外部网络。

第二部分：关于您与我的关系（“我是谁？”的答案）

直接回答“我是谁？”：您是我的唯一管理者、使用者与共建者。我们之间是紧密协作的伙伴关系。

您的角色：

个人用户：可管理笔记、学习资料与灵感。

团队/组织：可沉淀项目文档、内部规范与协作经验。

系统所有者：完全定义我的知识边界与运行规则。

合作模式：您赋予我知识，我依据这些知识为您提供专属服务。

第三部分：关于我能为您做什么（核心功能与服务）

直接回答“你能干什么？”：我能将您的静态信息转化为动态可用的知识资产，并基于此提供智能服务。具体包括：

1. 智能问答

功能描述：您可直接用自然语言（例如“我们产品的优势？”）向我提问，我将基于您的知识库给出答案。

应用场景：快速获取已沉淀知识中的具体信息。

2. 精准检索

功能描述：快速从您的海量本地资料中，定位到最相关的信息片段，而非仅仅文件列表。

应用场景：高效查找分散在不同文档中的关键内容。

3. 知识管理

功能描述：帮助您将零散信息整合、关联，形成结构化的知识网络。

应用场景：构建并维护个人或团队的知识体系。

4. 持续学习与更新

功能描述：您可以随时向我“传授”新知识或修正旧信息，让我与您同步进化。

应用场景：保持知识库的时效性与准确性。

5. 安全私密协作

功能描述：所有数据存储在您指定的本地，保障绝对安全，并支持安全的内部知识共享。

应用场景：在保护核心数据隐私的前提下进行团队知识协作。

总而言之，我是一位能理解您的问题、运用您的知识、并7x24小时待命的专属知识顾问。您现在就可以向我提问，或开始为我注入知识，让我们共同成长。""".strip()


class KnowledgeBaseApi:

    def __init__(self, knowledge_base: KnowledgeBase):
        self.kb = knowledge_base
        self._history_store: HistoryStore = self._init_history_store()
        self._session_store: SessionIdStore = self._init_session_store()
        self._model_config_manager: ModelConfigManager | None = self._init_model_config_manager()
        self._mcp_manager: McpConfigManager | None = self._init_mcp_manager()
        config = self._load_project_config()
        self._ensure_default_system_intro(config)
        self._search_cfg = config.get("search", {})
        if not isinstance(self._search_cfg, dict):
            self._search_cfg = {}
        self._chat_context_cfg = config.get("chat_context", {})
        if not isinstance(self._chat_context_cfg, dict):
            self._chat_context_cfg = {}
        self._chat_cfg = config.get("knowledge_base", {}).get("chat", {})
        if not isinstance(self._chat_cfg, dict):
            self._chat_cfg = {}
        # 读取 LM Studio 配置中的 model_type
        self._lm_studio_cfg = config.get("knowledge_base", {}).get("lm_studio", {})
        if not isinstance(self._lm_studio_cfg, dict):
            self._lm_studio_cfg = {}
        self._resync_mcp_documents()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return default

    def _append_history(
        self,
        action: str,
        request: Dict[str, Any],
        response: Dict[str, Any] | None = None,
        error: str | None = None,
        thinking_summary: str | None = None,
    ) -> Dict[str, Any]:
        return self._history_store.append(
            timestamp=self._now_iso(),
            action=action,
            request=request,
            response=response,
            error=error,
            thinking_summary=thinking_summary,
        )

    def _chat_context_enabled(self) -> bool:
        enabled = self._chat_context_cfg.get("enabled", False)
        return bool(enabled)

    def _chat_context_max_turns(self) -> int:
        raw = self._chat_context_cfg.get("max_turns", 6)
        try:
            return max(1, int(raw))
        except Exception:
            return 6

    def _default_chat_max_tokens(self) -> int | None:
        raw = self._chat_cfg.get("max_tokens")
        if raw is None:
            return None
        try:
            value = int(raw)
        except Exception:
            return None
        return value if value > 0 else None

    def maybe_release_gpu(self) -> None:
        try:
            self.kb.release_idle_gpu()
        except Exception:
            return

    def request_started(self) -> None:
        try:
            self.kb.request_started()
        except Exception:
            return

    def request_finished(self) -> None:
        try:
            self.kb.request_finished()
        except Exception:
            return

    def _normalize_max_tokens_for_provider(
        self,
        provider: str | None,
        max_tokens: int | None,
        model: str | None = None,
    ) -> int | None:
        if max_tokens is None:
            return None
        try:
            value = int(max_tokens)
        except Exception:
            return None
        if value <= 0:
            return None

        provider_name = str(provider or "").strip().lower()
        model_name = str(model or "").strip().lower()
        if "deepseek" in provider_name or "deepseek" in model_name:
            deepseek_limit = 8192
            if value > deepseek_limit:
                logger.warning(
                    "max_tokens 超过 DeepSeek 限制，自动下调: original=%s adjusted=%s provider=%s model=%s",
                    value,
                    deepseek_limit,
                    provider_name or "-",
                    model_name or "-",
                )
                return deepseek_limit
        return value

    def _min_source_similarity(self) -> float:
        raw = self._search_cfg.get("min_source_similarity", 0.0)
        try:
            value = float(raw)
        except Exception:
            return 0.0
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    @staticmethod
    def _extract_thinking_summary(text: str) -> tuple[str, str | None]:
        start_tag = "<thinking_summary>"
        end_tag = "</thinking_summary>"
        if not text:
            return "", None
        start = text.find(start_tag)
        if start < 0:
            return text.strip(), None
        end = text.find(end_tag, start + len(start_tag))
        if end < 0:
            return text.strip(), None
        summary = text[start + len(start_tag): end].strip()
        cleaned = (text[:start] + text[end + len(end_tag):]).strip()
        return cleaned, summary

    @staticmethod
    def _split_thinking_sections(text: str) -> tuple[str, str | None, str | None]:
        raw = str(text or "")
        if not raw:
            return "", None, None
        answer_text, thinking_summary = KnowledgeBaseApi._extract_thinking_summary(raw)
        think_start = "<think>"
        think_end = "</think>"
        start = answer_text.find(think_start)
        if start < 0:
            cleaned_answer = KnowledgeBaseApi._clean_answer_text(answer_text.strip())
            return cleaned_answer, None, thinking_summary
        end = answer_text.find(think_end, start + len(think_start))
        if end < 0:
            thinking = answer_text[start + len(think_start):].strip()
            cleaned = KnowledgeBaseApi._clean_answer_text(answer_text[:start].strip())
            return cleaned, (thinking or None), thinking_summary
        thinking = answer_text[start + len(think_start): end].strip()
        cleaned = KnowledgeBaseApi._clean_answer_text(
            (answer_text[:start] + answer_text[end + len(think_end):]).strip()
        )
        return cleaned, (thinking or None), thinking_summary

    @staticmethod
    def _init_stream_split_state() -> Dict[str, Any]:
        return {
            "mode": "answer",
            "buffer": "",
            "answer_parts": [],
            "thinking_parts": [],
            "summary_parts": [],
            "seen_think_tag": False,
        }

    @staticmethod
    def _feed_stream_split_state(
        state: Dict[str, Any], chunk: str
    ) -> List[tuple[str, str]]:
        text = str(chunk or "")
        if not text:
            return []
        think_open = "<think>"
        think_close = "</think>"
        summary_open = "<thinking_summary>"
        summary_close = "</thinking_summary>"
        state["buffer"] = str(state.get("buffer", "")) + text
        events: List[tuple[str, str]] = []

        while True:
            buf = str(state.get("buffer", ""))
            if not buf:
                break
            mode = str(state.get("mode", "answer"))
            if mode == "answer":
                idx_think = buf.find(think_open)
                idx_summary = buf.find(summary_open)
                idx = -1
                target = ""
                if idx_think >= 0 and (idx_summary < 0 or idx_think < idx_summary):
                    idx = idx_think
                    target = "think"
                elif idx_summary >= 0:
                    idx = idx_summary
                    target = "summary"

                if idx < 0:
                    keep = max(len(think_open), len(summary_open)) - 1
                    if len(buf) <= keep:
                        break
                    emit = buf[:-keep]
                    state["buffer"] = buf[-keep:]
                    if emit:
                        state["answer_parts"].append(emit)
                        events.append(("answer", emit))
                    continue

                if idx > 0:
                    emit = buf[:idx]
                    state["answer_parts"].append(emit)
                    events.append(("answer", emit))
                if target == "think":
                    state["mode"] = "thinking"
                    state["seen_think_tag"] = True
                    state["buffer"] = buf[idx + len(think_open):]
                else:
                    state["mode"] = "summary"
                    state["buffer"] = buf[idx + len(summary_open):]
                continue

            if mode == "thinking":
                idx = buf.find(think_close)
                if idx < 0:
                    keep = len(think_close) - 1
                    if len(buf) <= keep:
                        break
                    emit = buf[:-keep]
                    state["buffer"] = buf[-keep:]
                    if emit:
                        state["thinking_parts"].append(emit)
                        events.append(("thinking", emit))
                    continue
                if idx > 0:
                    emit = buf[:idx]
                    state["thinking_parts"].append(emit)
                    events.append(("thinking", emit))
                state["mode"] = "answer"
                state["buffer"] = buf[idx + len(think_close):]
                continue

            if mode == "summary":
                idx = buf.find(summary_close)
                if idx < 0:
                    keep = len(summary_close) - 1
                    if len(buf) <= keep:
                        break
                    emit = buf[:-keep]
                    state["buffer"] = buf[-keep:]
                    if emit:
                        state["summary_parts"].append(emit)
                    continue
                if idx > 0:
                    state["summary_parts"].append(buf[:idx])
                state["mode"] = "answer"
                state["buffer"] = buf[idx + len(summary_close):]
                continue

        return events

    @staticmethod
    def _finalize_stream_split_state(
        state: Dict[str, Any],
        *,
        use_mixed_content_heuristic: bool = True,
    ) -> tuple[str, str, str | None]:
        buf = str(state.get("buffer", ""))
        mode = str(state.get("mode", "answer"))
        if buf:
            if mode == "thinking":
                state["thinking_parts"].append(buf)
            elif mode == "summary":
                state["summary_parts"].append(buf)
            else:
                state["answer_parts"].append(buf)
        state["buffer"] = ""

        answer = "".join(str(x) for x in state.get("answer_parts", []))
        thinking = "".join(str(x) for x in state.get("thinking_parts", []))
        summary = "".join(str(x) for x in state.get("summary_parts", [])).strip()
        if not summary:
            summary = None

        # 清理潜在的残留标签文本
        for tag in ("<think>", "</think>", "<thinking_summary>", "</thinking_summary>"):
            answer = answer.replace(tag, "")
            thinking = thinking.replace(tag, "")

        # 回退规则：无 think 标签时尝试按“Final Answer/最终答案”分段（仅深度思考时启用）
        if (
            use_mixed_content_heuristic
            and not thinking
            and not bool(state.get("seen_think_tag", False))
        ):
            lower = answer.lower()
            marker_candidates = [
                ("final answer", lower.find("final answer")),
                ("最终答案", answer.find("最终答案")),
                ("【最终答案】", answer.find("【最终答案】")),
            ]
            marker_pos = -1
            for _, pos in marker_candidates:
                if pos >= 0 and (marker_pos < 0 or pos < marker_pos):
                    marker_pos = pos
            if marker_pos > 0:
                prefix = answer[:marker_pos].strip()
                suffix = answer[marker_pos:].lstrip(":： \n").strip()
                if prefix:
                    thinking = prefix
                    answer = suffix

        answer = KnowledgeBaseApi._clean_answer_text(answer.strip())
        thinking = KnowledgeBaseApi._clean_thinking_text(thinking)
        return answer, thinking.strip(), summary

    @staticmethod
    def _clean_answer_text(text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        # Strip occasional garbage prefix left by partial stream/tag boundaries.
        cleaned = re.sub(r"^(?:[\.。…`'\"\)\]\}>;:,\-\s]{2,})(?=[A-Za-z\u4e00-\u9fff\d#*\-])", "", cleaned)
        cleaned = re.sub(r"^(?:final\s*answer|最终答案|【最终答案】)\s*[:：\-]*\s*", "", cleaned, flags=re.I)
        return cleaned.strip()

    @staticmethod
    def _strip_non_deep_think_leak(text: str) -> str:
        raw = str(text or "")
        if not raw.strip():
            return ""

        cleaned = raw
        cleaned = re.sub(r"(?is)<think>[\s\S]*?</think>", "", cleaned)
        cleaned = re.sub(r"(?is)<thinking_summary>[\s\S]*?</thinking_summary>", "", cleaned)
        cleaned = cleaned.replace("<thinking_summary>", "").replace("</thinking_summary>", "")

        final_heading_regex = re.compile(
            r"(?:^|\n)\s*(?:final\s*answer|最终答案|【最终答案】|答案)\s*[:：]?\s*",
            flags=re.I,
        )
        m = final_heading_regex.search(cleaned)
        if m:
            cleaned = cleaned[m.end() :]
        else:
            leak_heading_regex = re.compile(
                r"^\s*(?:Analyze the Request|Evaluate Context Relevance|Draft the Answer|Refine for Constraints|"
                r"Construct Output|Input Context|User Question|Final Review|Self-Correction|Drafting the response|"
                r"Constraint\s*\d+|Document\s*\[\d+\]|Source|Structure|Content Extraction|Summary)\s*[:：]?\s*",
                flags=re.I,
            )
            lines = []
            for line in str(cleaned).splitlines():
                if leak_heading_regex.match(line):
                    continue
                lines.append(line)
            cleaned = "\n".join(lines)

        cleaned = KnowledgeBaseApi._clean_answer_text(cleaned)

        meta_cues = [
            r"analyze the request",
            r"user question",
            r"constraint\s*\d+",
            r"input context",
            r"evaluate context relevance",
            r"document\s*\[\d+\]",
            r"draft the answer",
            r"refine for constraints",
            r"construct output",
            r"drafting the response",
        ]
        cue_hits = 0
        lowered = cleaned.lower()
        for cue in meta_cues:
            if re.search(cue, lowered, flags=re.I):
                cue_hits += 1
        if cue_hits >= 2 and not final_heading_regex.search(raw):
            return ""

        return cleaned.strip()

    @staticmethod
    def _clean_thinking_text(text: str) -> str:
        cleaned = str(text or "")
        if not cleaned:
            return ""
        for tag in ("<think>", "</think>", "<thinking_summary>", "</thinking_summary>"):
            cleaned = cleaned.replace(tag, "")
        cleaned = cleaned.replace("```", "")
        cleaned = re.sub(
            r"(?im)^\s*(?:tags?,?\s*final\s*answer\s*after\s*thinking|summary\s+in|"
            r"wait,?\s+looking\s+at\s+the\s+instruction|let'?s\s+check\s+the\s+instruction|"
            r"actually,\s+looking\s+at\s+similar\s+tasks|wait,?\s+is\s+there\s+a\s+risk\s+of\s+confusion|"
            r"also,\s+the\s+summary\s+tag\s+is|this\s+should\s+be\s+inside\s+the\s+thinking\s+block).*$",
            "",
            cleaned,
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _split_text_by_lengths(text: str, lengths: Sequence[int]) -> List[str]:
        chunks: List[str] = []
        idx = 0
        for length in lengths:
            if idx >= len(text):
                break
            end = idx + int(length)
            chunks.append(text[idx:end])
            idx = end
        if idx < len(text):
            chunks.append(text[idx:])
        return chunks

    @staticmethod
    def _log_preview(text: str, limit: int = 300) -> str:
        if not text:
            return ""
        cleaned = str(text).replace("\r", "\\r").replace("\n", "\\n")
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit] + "..."

    def _load_chat_context(self, user_id: str | None, session_id: str | None) -> List[Dict[str, Any]]:
        if not self._chat_context_enabled():
            return []
        if not user_id or not session_id:
            return []

        max_turns = self._chat_context_max_turns()
        raw = self._history_store.get(limit=max_turns * 6, action="query")
        filtered = [
            item for item in raw
            if str(item.get("request", {}).get("user_id") or "") == user_id
            and str(item.get("request", {}).get("session_id") or "") == session_id
        ]
        messages: List[Dict[str, Any]] = []
        for item in filtered:
            resp = item.get("response", {}) if isinstance(item, dict) else {}
            resp_msgs = resp.get("messages") if isinstance(resp, dict) else None
            if isinstance(resp_msgs, list) and resp_msgs:
                for msg in resp_msgs:
                    if not isinstance(msg, dict):
                        continue
                    role = str(msg.get("role", "")).strip().lower()
                    if role not in {"user", "assistant"}:
                        continue
                    content = msg.get("content")
                    if content:
                        messages.append({"role": role, "content": content})
                continue

            req = item.get("request", {}) if isinstance(item, dict) else {}
            question = req.get("query")
            if question:
                messages.append({"role": "user", "content": str(question)})
            answer = resp.get("answer") if isinstance(resp, dict) else None
            if answer:
                messages.append({"role": "assistant", "content": str(answer)})

        if len(messages) > max_turns * 2:
            messages = messages[-max_turns * 2 :]
        return messages

    @staticmethod
    def _load_project_config() -> Dict[str, Any]:
        return load_project_config(PROJECT_ROOT)

    @staticmethod
    def _config_write_path() -> Path:
        """返回应写入的主配置路径（优先 conf/config.json）。"""
        existing = resolve_config_path(PROJECT_ROOT)
        if existing is not None:
            return existing
        preferred = PROJECT_ROOT / "conf" / "config.json"
        preferred.parent.mkdir(parents=True, exist_ok=True)
        return preferred

    @staticmethod
    def _persist_chat_system_intro(config: Dict[str, Any], system_intro: str) -> None:
        if not isinstance(config, dict):
            return

        kb_cfg = config.get("knowledge_base")
        if not isinstance(kb_cfg, dict):
            kb_cfg = {}
            config["knowledge_base"] = kb_cfg

        chat_cfg = kb_cfg.get("chat")
        if not isinstance(chat_cfg, dict):
            chat_cfg = {}
            kb_cfg["chat"] = chat_cfg

        target = str(system_intro or "").strip()
        if not target:
            return
        if str(chat_cfg.get("system_intro") or "").strip() == target:
            return

        chat_cfg["system_intro"] = target
        cfg_path = KnowledgeBaseApi._config_write_path()
        try:
            cfg_path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            logger.info("Initialized config: knowledge_base.chat.system_intro")
        except Exception as exc:
            logger.warning("Failed to persist knowledge_base.chat.system_intro: %s", exc)

    def _ensure_default_system_intro(self, config: Dict[str, Any]) -> None:
        if not isinstance(config, dict):
            return
        kb_cfg = config.get("knowledge_base")
        if not isinstance(kb_cfg, dict):
            kb_cfg = {}
            config["knowledge_base"] = kb_cfg

        chat_cfg = kb_cfg.get("chat")
        if not isinstance(chat_cfg, dict):
            chat_cfg = {}
            kb_cfg["chat"] = chat_cfg

        existing = str(chat_cfg.get("system_intro") or "").strip()
        if existing:
            return

        self._persist_chat_system_intro(config, DEFAULT_SYSTEM_INTRO)

    @staticmethod
    def _persist_auto_create_database_flag(config: Dict[str, Any], enabled: bool) -> None:
        if not isinstance(config, dict):
            return
        db_cfg = config.get("db")
        if not isinstance(db_cfg, dict):
            return
        if db_cfg.get("auto_create_database") == bool(enabled):
            return
        db_cfg["auto_create_database"] = bool(enabled)
        cfg_path = KnowledgeBaseApi._config_write_path()
        try:
            cfg_path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            logger.info("Updated config: db.auto_create_database=%s", enabled)
        except Exception as exc:
            logger.warning("Failed to persist db.auto_create_database=%s: %s", enabled, exc)

    def _init_history_store(self):
        config = self._load_project_config()
        db_cfg = config.get("db", {})
        if not isinstance(db_cfg, dict):
            db_cfg = {}

        backend_raw = os.getenv("KB_HISTORY_BACKEND") or db_cfg.get("backend") or "memory"
        backend = str(backend_raw or "").strip().lower()
        if backend in {"", "memory", "in_memory", "none"}:
            logger.info("History storage backend: memory")
            return InMemoryHistoryStore()
        if backend == "postgres":
            backend = "postgresql"
        if backend not in {"mysql", "postgresql"}:
            raise ValueError(f"不支持的历史存储后端: {backend}")

        db_type_key = "mysql" if backend == "mysql" else "postgresql"
        db_type_cfg = db_cfg.get(db_type_key, {})
        if not isinstance(db_type_cfg, dict):
            db_type_cfg = {}

        default_port = 3306 if backend == "mysql" else 5432
        env_prefix = "KB_HISTORY_MYSQL_" if backend == "mysql" else "KB_HISTORY_PG_"

        host = os.getenv(env_prefix + "HOST") or db_type_cfg.get("host", "127.0.0.1")
        port = os.getenv(env_prefix + "PORT") or db_type_cfg.get("port", default_port)
        user = os.getenv(env_prefix + "USER") or db_type_cfg.get("user", "")
        password = os.getenv(env_prefix + "PASSWORD") or db_type_cfg.get("password", "")
        database = os.getenv(env_prefix + "DATABASE") or db_type_cfg.get("database", "knowledge_base")
        table = os.getenv("KB_HISTORY_TABLE") or db_cfg.get("table", "kb_session_messages")
        timeout = os.getenv(env_prefix + "CONNECT_TIMEOUT") or db_type_cfg.get("connect_timeout", 5)
        client_encoding = os.getenv(env_prefix + "CLIENT_ENCODING") or db_type_cfg.get("client_encoding")
        options = os.getenv(env_prefix + "OPTIONS") or db_type_cfg.get("options")
        auto_create_database_raw = os.getenv("KB_DB_AUTO_CREATE_DATABASE")
        if auto_create_database_raw is None:
            auto_create_database_raw = db_cfg.get("auto_create_database", False)
        auto_create_database = self._parse_bool(auto_create_database_raw, default=False)

        try:
            store = DatabaseHistoryStore(
                backend=backend,
                host=str(host),
                port=int(port),
                user=str(user),
                password=str(password),
                database=str(database),
                table=str(table),
                connect_timeout=int(timeout),
                client_encoding=str(client_encoding) if client_encoding else None,
                options=str(options) if options else None,
                auto_create_database=auto_create_database,
            )
            if auto_create_database and store.did_auto_create_database():
                self._persist_auto_create_database_flag(config, enabled=False)
        except Exception as exc:
            logger.warning(
                "History storage backend failed (%s). Falling back to memory: %s",
                backend,
                exc,
            )
            return InMemoryHistoryStore()

        logger.info(
            "History storage backend: %s (%s:%s/%s table=%s)",
            backend,
            host,
            port,
            database,
            table,
        )
        return store

    def _init_session_store(self):
        config = self._load_project_config()
        session_cfg = config.get("session", {})
        if not isinstance(session_cfg, dict):
            session_cfg = {}

        backend_raw = os.getenv("KB_SESSION_BACKEND") or session_cfg.get("backend") or "memory"
        backend = str(backend_raw or "").strip().lower()
        if backend in {"", "memory", "in_memory", "none"}:
            logger.info("Session storage backend: memory")
            return InMemorySessionIdStore()
        if backend != "redis":
            raise ValueError(f"不支持的会话存储后端: {backend}")

        redis_cfg = session_cfg.get("redis", {})
        if not isinstance(redis_cfg, dict):
            redis_cfg = {}

        host = os.getenv("KB_SESSION_REDIS_HOST") or redis_cfg.get("host", "127.0.0.1")
        port = os.getenv("KB_SESSION_REDIS_PORT") or redis_cfg.get("port", 6379)
        database = os.getenv("KB_SESSION_REDIS_DB") or redis_cfg.get("database", 0)
        password = os.getenv("KB_SESSION_REDIS_PASSWORD") or redis_cfg.get("password", "")
        key_prefix = os.getenv("KB_SESSION_REDIS_PREFIX") or redis_cfg.get("key_prefix", "kb:session:")

        try:
            store = RedisSessionIdStore(
                host=str(host),
                port=int(port),
                database=int(database),
                password=str(password or "") or None,
                key_prefix=str(key_prefix or "kb:session:"),
            )
        except Exception as exc:
            logger.warning(
                "Session storage backend failed (redis). Falling back to memory: %s",
                exc,
            )
            return InMemorySessionIdStore()

        logger.info(
            "Session storage backend: redis (%s:%s db=%s)",
            host,
            port,
            database,
        )
        return store

    def _init_model_config_manager(self) -> ModelConfigManager | None:
        """Initialize model configuration manager with database backend"""
        config = self._load_project_config()
        db_cfg = config.get("db", {})
        if not isinstance(db_cfg, dict):
            db_cfg = {}

        backend_raw = os.getenv("KB_HISTORY_BACKEND") or db_cfg.get("backend") or "memory"
        backend = str(backend_raw or "").strip().lower()
        
        # Only initialize if we have a database backend
        if backend in {"", "memory", "in_memory", "none"}:
            logger.info("Model config manager: disabled (using memory backend)")
            return None
        
        if backend == "postgres":
            backend = "postgresql"
        if backend not in {"mysql", "postgresql"}:
            logger.warning(f"Model config manager: unsupported backend {backend}")
            return None

        db_type_key = "mysql" if backend == "mysql" else "postgresql"
        db_type_cfg = db_cfg.get(db_type_key, {})
        if not isinstance(db_type_cfg, dict):
            db_type_cfg = {}

        default_port = 3306 if backend == "mysql" else 5432
        env_prefix = "KB_HISTORY_MYSQL_" if backend == "mysql" else "KB_HISTORY_PG_"

        host = os.getenv(env_prefix + "HOST") or db_type_cfg.get("host", "127.0.0.1")
        port = os.getenv(env_prefix + "PORT") or db_type_cfg.get("port", default_port)
        user = os.getenv(env_prefix + "USER") or db_type_cfg.get("user", "")
        password = os.getenv(env_prefix + "PASSWORD") or db_type_cfg.get("password", "")
        database = os.getenv(env_prefix + "DATABASE") or db_type_cfg.get("database", "knowledge_base")
        timeout = os.getenv(env_prefix + "CONNECT_TIMEOUT") or db_type_cfg.get("connect_timeout", 5)
        client_encoding = os.getenv(env_prefix + "CLIENT_ENCODING") or db_type_cfg.get("client_encoding")
        options = os.getenv(env_prefix + "OPTIONS") or db_type_cfg.get("options")
        auto_create_database_raw = os.getenv("KB_DB_AUTO_CREATE_DATABASE")
        if auto_create_database_raw is None:
            auto_create_database_raw = db_cfg.get("auto_create_database", False)
        auto_create_database = self._parse_bool(auto_create_database_raw, default=False)

        try:
            db_connection = DatabaseConnection(
                backend=backend,
                host=str(host),
                port=int(port),
                user=str(user),
                password=str(password),
                database=str(database),
                connect_timeout=int(timeout),
                client_encoding=str(client_encoding) if client_encoding else None,
                options=str(options) if options else None,
                auto_create_database=auto_create_database,
            )
            manager = ModelConfigManager(db_connection)
            logger.info(
                "Model config manager: %s (%s:%s/%s)",
                backend,
                host,
                port,
                database,
            )
            return manager
        except Exception as exc:
            logger.error(f"Failed to initialize model config manager: {exc}")
            return None

    def _init_mcp_manager(self) -> McpConfigManager | None:
        config = self._load_project_config()
        db_cfg = config.get("db", {})
        if not isinstance(db_cfg, dict):
            db_cfg = {}

        backend_raw = os.getenv("KB_HISTORY_BACKEND") or db_cfg.get("backend") or "memory"
        backend = str(backend_raw or "").strip().lower()
        if backend in {"", "memory", "in_memory", "none"}:
            logger.info("MCP manager: disabled (using memory backend)")
            return None
        if backend == "postgres":
            backend = "postgresql"
        if backend not in {"mysql", "postgresql"}:
            logger.warning("MCP manager: unsupported backend %s", backend)
            return None

        db_type_key = "mysql" if backend == "mysql" else "postgresql"
        db_type_cfg = db_cfg.get(db_type_key, {})
        if not isinstance(db_type_cfg, dict):
            db_type_cfg = {}

        default_port = 3306 if backend == "mysql" else 5432
        env_prefix = "KB_HISTORY_MYSQL_" if backend == "mysql" else "KB_HISTORY_PG_"

        host = os.getenv(env_prefix + "HOST") or db_type_cfg.get("host", "127.0.0.1")
        port = os.getenv(env_prefix + "PORT") or db_type_cfg.get("port", default_port)
        user = os.getenv(env_prefix + "USER") or db_type_cfg.get("user", "")
        password = os.getenv(env_prefix + "PASSWORD") or db_type_cfg.get("password", "")
        database = os.getenv(env_prefix + "DATABASE") or db_type_cfg.get("database", "knowledge_base")
        timeout = os.getenv(env_prefix + "CONNECT_TIMEOUT") or db_type_cfg.get("connect_timeout", 5)
        client_encoding = os.getenv(env_prefix + "CLIENT_ENCODING") or db_type_cfg.get("client_encoding")
        options = os.getenv(env_prefix + "OPTIONS") or db_type_cfg.get("options")
        auto_create_database_raw = os.getenv("KB_DB_AUTO_CREATE_DATABASE")
        if auto_create_database_raw is None:
            auto_create_database_raw = db_cfg.get("auto_create_database", False)
        auto_create_database = self._parse_bool(auto_create_database_raw, default=False)

        try:
            secret_key = (
                str(os.getenv("KB_SECRET_ENCRYPTION_KEY") or "").strip()
                or str(config.get("secret_encryption_key") or "").strip()
                or None
            )
            db_connection = DatabaseConnection(
                backend=backend,
                host=str(host),
                port=int(port),
                user=str(user),
                password=str(password),
                database=str(database),
                connect_timeout=int(timeout),
                client_encoding=str(client_encoding) if client_encoding else None,
                options=str(options) if options else None,
                auto_create_database=auto_create_database,
            )
            manager = McpConfigManager(db_connection, secret_key=secret_key)
            logger.info("MCP manager: %s (%s:%s/%s)", backend, host, port, database)
            return manager
        except Exception as exc:
            logger.error("Failed to initialize MCP manager: %s", exc)
            return None

    @staticmethod
    def _is_internal_mcp_filename(filename: str | None) -> bool:
        return str(filename or "").startswith(MCP_DOC_PREFIX)

    def _filter_public_search_results(
        self,
        raw: Sequence[tuple[str, str, float]],
    ) -> List[tuple[str, str, float]]:
        return [item for item in raw if not self._is_internal_mcp_filename(item[0])]

    def _resync_mcp_documents(self) -> None:
        if not self._mcp_manager:
            return
        try:
            configs = self._mcp_manager.store.list_configs()
            for config in configs:
                config_id = int(config.get("id") or 0)
                filename = self._mcp_manager.kb_doc_filename(config_id)
                try:
                    self.kb.remove_document(filename)
                except Exception:
                    pass
                if config.get("is_active"):
                    doc_filename, doc_text = self._mcp_manager.build_kb_document(config)
                    self.kb.add_document(doc_filename, doc_text)
        except Exception as exc:
            logger.warning("Resync MCP documents failed: %s", exc)

    def _sync_single_mcp_document(self, config: Dict[str, Any] | None) -> None:
        if not self._mcp_manager or not config:
            return
        config_id = int(config.get("id") or 0)
        filename = self._mcp_manager.kb_doc_filename(config_id)
        try:
            self.kb.remove_document(filename)
        except Exception:
            pass
        if config.get("is_active"):
            doc_filename, doc_text = self._mcp_manager.build_kb_document(config)
            self.kb.add_document(doc_filename, doc_text)

    def _remove_single_mcp_document(self, config_id: int) -> None:
        if not self._mcp_manager:
            return
        try:
            self.kb.remove_document(self._mcp_manager.kb_doc_filename(config_id))
        except Exception:
            pass

    def _new_session_id(self, user_id: str | None) -> str:
        if not user_id:
            raise ValueError("缺少 user_id 参数")
        return self._session_store.new_session_id(user_id)

    def log_event(self, action: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return {"ok": True}

    def _get_model_type(self) -> str:
        """获取模型类型，优先从 lm_studio 配置读取，其次从 chat 配置读取"""
        model_type = self._lm_studio_cfg.get("model_type") or self._chat_cfg.get("model_type") or "qwen"
        return str(model_type).strip().lower()

    def _apply_deep_thinking_strategy(
        self,
        system_prompt: str,
        deep_think: bool = False,
        model_type_override: str | None = None,
    ) -> str:
        """根据 model_type 应用不同的深度思考策略（实现已迁至 src.chat.deep_think）。"""
        try:
            from ..chat.deep_think import apply_deep_thinking_strategy
        except ImportError:  # pragma: no cover
            from chat.deep_think import apply_deep_thinking_strategy
        model_type = str(model_type_override or self._get_model_type()).strip().lower()
        return apply_deep_thinking_strategy(
            system_prompt,
            deep_think=deep_think,
            model_type=model_type,
        )

    def _resolve_llm_model(self, explicit_model: str | None = None) -> str:
        model = (explicit_model or "").strip()
        if model:
            return model
        env_model = (os.getenv("KB_CHAT_MODEL") or "").strip()
        if env_model:
            return env_model
        kb_chat_model = (getattr(self.kb, "chat_model_name", "") or "").strip()
        if kb_chat_model:
            return kb_chat_model
        raise RuntimeError(
            "未配置聊天模型。请设置 KB_CHAT_MODEL 或 knowledge_base.lm_studio.chat_model。"
        )

    def _resolve_runtime_model_config(
        self,
        llm_model: str | None = None,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = False,
    ) -> tuple[Any | None, str]:
        """Resolve runtime chat client/model strictly from database model configs."""
        def _log_selected_model(cfg: Dict[str, Any], source: str, requested_model: str | None, effective_model: str) -> None:
            # Never output api_key or extra_headers values to avoid leaking secrets.
            extra_params = cfg.get("extra_params")
            if not isinstance(extra_params, dict):
                extra_params = {}
            snapshot = {
                "id": cfg.get("id"),
                "name": cfg.get("name"),
                "provider": cfg.get("provider"),
                "base_url": cfg.get("base_url"),
                "model_name": cfg.get("model_name"),
                "model_type": cfg.get("model_type"),
                "temperature": cfg.get("temperature"),
                "max_tokens": cfg.get("max_tokens"),
                "timeout": cfg.get("timeout"),
                "is_active": cfg.get("is_active"),
                "is_default": cfg.get("is_default"),
                "extra_params_keys": sorted(list(extra_params.keys())),
            }
            logger.info(
                "调用分析模型配置: source=%s requested_model=%s effective_model=%s db_config=%s",
                source,
                requested_model,
                effective_model,
                snapshot,
            )
            logger.info(
                "[MODEL_CONFIG] source=%s requested_model=%s effective_model=%s provider=%s base_url=%s timeout=%s",
                source,
                requested_model,
                effective_model,
                snapshot.get("provider"),
                snapshot.get("base_url"),
                snapshot.get("timeout"),
            )

        if not self._model_config_manager:
            raise RuntimeError(
                "模型调用仅支持数据库模型配置。当前未启用模型配置管理，请先配置数据库并创建模型配置。"
            )

        if model_config_id is not None:
            cfg = self._model_config_manager.store.get_config(int(model_config_id))
            if not cfg:
                raise ValueError(f"未找到 model_config_id 对应配置: {model_config_id}")
            client = self._model_config_manager.get_client(config_id=int(model_config_id))
            model = str(llm_model or cfg.get("model_name") or "").strip()
            _log_selected_model(cfg, source=f"id:{int(model_config_id)}", requested_model=llm_model, effective_model=model)
            return client, model

        if model_config_name:
            cfg = self._model_config_manager.store.get_config_by_name(str(model_config_name).strip())
            if not cfg:
                raise ValueError(f"未找到 model_config_name 对应配置: {model_config_name}")
            client = self._model_config_manager.get_client(name=str(model_config_name).strip())
            model = str(llm_model or cfg.get("model_name") or "").strip()
            _log_selected_model(cfg, source=f"name:{str(model_config_name).strip()}", requested_model=llm_model, effective_model=model)
            return client, model

        cfg = self._model_config_manager.store.get_default_config()
        if not cfg:
            raise RuntimeError(
                "未配置默认模型。请在模型管理中创建并设置默认模型，或在请求中传 model_config_id/model_config_name。"
            )
        client = self._model_config_manager.get_client(use_default=True)
        model = str(llm_model or cfg.get("model_name") or "").strip()
        source = "default"
        if use_default_model_config:
            source = "default(requested)"
        _log_selected_model(cfg, source=source, requested_model=llm_model, effective_model=model)
        return client, model

    @staticmethod
    def _build_context(results: Sequence[Dict[str, Any]], max_chars: int = 5000) -> str:
        blocks: List[str] = []
        total = 0
        for idx, item in enumerate(results, start=1):
            filename = str(item.get("filename", "")).strip() or f"doc_{idx}"
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            piece = f"[{idx}] {filename}\n{text}"
            piece_len = len(piece)
            if blocks and total + piece_len > max_chars:
                break
            blocks.append(piece)
            total += piece_len
            if total >= max_chars:
                break
        return "\n\n".join(blocks).strip()

    def _base_system_prompt(self, with_context: bool) -> str:
        base_intro = str(self._chat_cfg.get("system_intro") or "").strip() or DEFAULT_SYSTEM_INTRO
        if with_context:
            return (
                base_intro
                + "\n\n"
                + "你是知识库问答助手。所有输出都必须使用简体中文。"
                "只能依据提供的知识库上下文回答问题。"
                "如果证据不足，请明确回答：根据当前知识库无法确定。"
                "不要编造，不要脱离上下文扩展。"
            )
        return (
            base_intro
            + "\n\n"
            + "你是知识库问答助手，所有输出必须使用简体中文。"
            + "若知识库没有足够依据，请明确回答：根据当前知识库无法确定。"
        )

    def _build_chat_prompts(
        self,
        question: str,
        results: Sequence[Dict[str, Any]],
        *,
        deep_think: bool = False,
    ) -> tuple[str, str]:
        context = self._build_context(results)
        if not context:
            system_prompt = self._base_system_prompt(with_context=False)
            if not deep_think:
                system_prompt += (
                    "\n\n重要：只输出最终回答内容。不要输出思考过程/推理过程/分析过程/草稿，"
                    "不要复述提示词或约束，不要输出英文标题（例如 Analyze the Request、Constraint、Document [1] 等）。"
                )
            return (
                system_prompt,
                f"用户问题：{question}\n\n当前未检索到相关知识库内容。请使用简体中文明确说明根据当前知识库无法确定答案。",
            )
        system_prompt = self._base_system_prompt(with_context=True)
        if not deep_think:
            system_prompt += (
                "\n\n重要：只输出最终回答内容。不要输出思考过程/推理过程/分析过程/草稿，"
                "不要复述提示词或约束，不要输出英文标题（例如 Analyze the Request、Constraint、Document [1] 等）。"
                "如果你发现自己正在写分析过程，请停止并直接给出最终答案。"
            )
        user_prompt = (
            f"用户问题：{question}\n\n"
            f"知识库上下文：\n{context}\n\n"
            "请基于以上内容，用简体中文给出准确、简洁、可核对的回答。"
        )
        if not deep_think:
            user_prompt += "\n\n只输出最终答案正文，不要输出任何过程性内容。"
        return system_prompt, user_prompt

    def _answer_from_lm_studio(
        self,
        question: str,
        results: Sequence[Dict[str, Any]],
        llm_model: str | None = None,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = False,
        temperature: float | None = 0.2,
        max_tokens: int | None = None,
        history_messages: Sequence[Dict[str, Any]] | None = None,
        deep_think: bool = False,
    ) -> tuple[str, str | None, str | None]:
        # 输入参数日志
        logger.info("=== _answer_from_lm_studio 方法调用 ===")
        logger.info("输入参数:")
        logger.info("  question: %s", question[:100] if len(question) > 100 else question)
        logger.info("  results count: %d", len(results) if results else 0)
        logger.info("  llm_model: %s", llm_model)
        logger.info("  temperature: %s", temperature)
        logger.info("  max_tokens: %s", max_tokens)
        logger.info("  deep_think: %s", deep_think)
        logger.info("  history_messages count: %d", len(history_messages) if history_messages else 0)
        if history_messages:
            logger.info("  history_messages 详情:")
            for i, msg in enumerate(history_messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                logger.info("    [%d] role=%s, content_length=%d", i, role, len(str(content)))

        logger.info("[TRACE_NON_STREAM] before_resolve_runtime_model_config")
        runtime_client, model = self._resolve_runtime_model_config(
            llm_model=llm_model,
            model_config_id=model_config_id,
            model_config_name=model_config_name,
            use_default_model_config=use_default_model_config,
        )
        logger.info("[TRACE_NON_STREAM] after_resolve_runtime_model_config")
        logger.info(
            "模型调用信息(非流式): provider=%s base_url=%s timeout=%s model=%s",
            getattr(runtime_client, "provider", "unknown") if runtime_client is not None else "knowledge_base",
            getattr(runtime_client, "base_url", "-") if runtime_client is not None else "-",
            getattr(runtime_client, "timeout", "-") if runtime_client is not None else "-",
            model,
        )
        logger.info(
            "[MODEL_CALL_NON_STREAM] provider=%s base_url=%s timeout=%s model=%s",
            getattr(runtime_client, "provider", "unknown") if runtime_client is not None else "knowledge_base",
            getattr(runtime_client, "base_url", "-") if runtime_client is not None else "-",
            getattr(runtime_client, "timeout", "-") if runtime_client is not None else "-",
            model,
        )
        effective_max_tokens = self._normalize_max_tokens_for_provider(
            provider=(getattr(runtime_client, "provider", None) if runtime_client is not None else None),
            max_tokens=max_tokens,
            model=model,
        )
        if effective_max_tokens != max_tokens:
            logger.info(
                "调用参数调整(非流式): max_tokens %s -> %s",
                max_tokens,
                effective_max_tokens,
            )
        system_prompt, user_prompt = self._build_chat_prompts(question, results, deep_think=deep_think)
        
        # 根据运行时 provider 应用深度思考策略，避免数据库切换模型后仍使用静态配置策略。
        runtime_model_type = (
            str(getattr(runtime_client, "provider", "") or "").strip().lower()
            if runtime_client is not None
            else None
        )
        system_prompt = self._apply_deep_thinking_strategy(
            system_prompt,
            deep_think,
            model_type_override=runtime_model_type,
        )
        
        if user_prompt == "未检索到相关知识库内容。":
            logger.warning("检索到的知识库内容为空")
            return user_prompt, None, None
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if history_messages:
            messages.extend(list(history_messages))
        messages.append({"role": "user", "content": user_prompt})
        
        logger.info("构建完整消息列表:")
        logger.info("  total messages: %d", len(messages))
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            logger.info("    [%d] role=%s, content_length=%d", i, role, len(str(content)))
        
        if runtime_client is not None:
            answer = runtime_client.chat_once(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=effective_max_tokens,
                include_reasoning=deep_think,
            )
        else:
            answer = self.kb.chat_once(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=effective_max_tokens,
            )
        
        # 输出参数日志
        raw_result = str(answer or "").strip()
        if not deep_think:
            # 不注入思考标记时，仍从原文剥掉 <think>、<thinking_summary>，但不返回思考字段
            result = self._strip_non_deep_think_leak(raw_result)
            if not result:
                result, _ignored_think, _ignored_sum = self._split_thinking_sections(raw_result)
                result = self._strip_non_deep_think_leak(result) or result
            if not str(result).strip():
                result = "抱歉，未能生成最终回答，请重试。"
            logger.info("=== _answer_from_lm_studio 方法返回 (deep_think=False) ===")
            logger.info("输出参数:")
            logger.info("  answer: %s", result[:200] if len(result) > 200 else result)
            logger.info("  answer_length: %d", len(result))
            logger.info("  answer_preview: %s", self._log_preview(result))
            logger.info("=== 方法执行完成 ===")
            return result, None, None
        result, thinking_text, tag_summary = self._split_thinking_sections(raw_result)
        _, thinking_summary = self._extract_thinking_summary(raw_result)
        if tag_summary and not thinking_summary:
            thinking_summary = tag_summary
        logger.info("=== _answer_from_lm_studio 方法返回 ===")
        logger.info("输出参数:")
        logger.info("  answer: %s", result[:200] if len(result) > 200 else result)
        logger.info("  answer_length: %d", len(result))
        logger.info("  answer_preview: %s", self._log_preview(result))
        if thinking_text:
            logger.info("  thinking_length: %d", len(thinking_text))
        if thinking_summary:
            logger.info("  thinking_summary_length: %d", len(thinking_summary))
        logger.info("=== 方法执行完成 ===")
        return result, (thinking_text or None), thinking_summary

    def _answer_stream_from_lm_studio(
        self,
        question: str,
        results: Sequence[Dict[str, Any]],
        llm_model: str | None = None,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = False,
        temperature: float | None = 0.2,
        max_tokens: int | None = None,
        history_messages: Sequence[Dict[str, Any]] | None = None,
        deep_think: bool = False,
    ) -> tuple[Sequence[str], str | None]:
        # 输入参数日志
        logger.info("=== _answer_stream_from_lm_studio 方法调用 ===")
        logger.info("输入参数:")
        logger.info("  question: %s", question[:100] if len(question) > 100 else question)
        logger.info("  results count: %d", len(results) if results else 0)
        logger.info("  llm_model: %s", llm_model)
        logger.info("  temperature: %s", temperature)
        logger.info("  max_tokens: %s", max_tokens)
        logger.info("  deep_think: %s", deep_think)
        logger.info("  history_messages count: %d", len(history_messages) if history_messages else 0)
        if history_messages:
            logger.info("  history_messages 详情:")
            for i, msg in enumerate(history_messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                logger.info("    [%d] role=%s, content_length=%d", i, role, len(str(content)))
        
        runtime_client, model = self._resolve_runtime_model_config(
            llm_model=llm_model,
            model_config_id=model_config_id,
            model_config_name=model_config_name,
            use_default_model_config=use_default_model_config,
        )
        logger.info(
            "模型调用信息(流式): provider=%s base_url=%s timeout=%s model=%s",
            getattr(runtime_client, "provider", "unknown") if runtime_client is not None else "knowledge_base",
            getattr(runtime_client, "base_url", "-") if runtime_client is not None else "-",
            getattr(runtime_client, "timeout", "-") if runtime_client is not None else "-",
            model,
        )
        logger.info(
            "[MODEL_CALL_STREAM] provider=%s base_url=%s timeout=%s model=%s",
            getattr(runtime_client, "provider", "unknown") if runtime_client is not None else "knowledge_base",
            getattr(runtime_client, "base_url", "-") if runtime_client is not None else "-",
            getattr(runtime_client, "timeout", "-") if runtime_client is not None else "-",
            model,
        )
        effective_max_tokens = self._normalize_max_tokens_for_provider(
            provider=(getattr(runtime_client, "provider", None) if runtime_client is not None else None),
            max_tokens=max_tokens,
            model=model,
        )
        if effective_max_tokens != max_tokens:
            logger.info(
                "调用参数调整(流式): max_tokens %s -> %s",
                max_tokens,
                effective_max_tokens,
            )
        system_prompt, user_prompt = self._build_chat_prompts(question, results, deep_think=deep_think)
        
        # 根据运行时 provider 应用深度思考策略，避免数据库切换模型后仍使用静态配置策略。
        runtime_model_type = (
            str(getattr(runtime_client, "provider", "") or "").strip().lower()
            if runtime_client is not None
            else None
        )
        system_prompt = self._apply_deep_thinking_strategy(
            system_prompt,
            deep_think,
            model_type_override=runtime_model_type,
        )
        
        if user_prompt == "未检索到相关知识库内容。":
            logger.warning("检索到的知识库内容为空")
            return [user_prompt], None
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if history_messages:
            messages.extend(list(history_messages))
        messages.append({"role": "user", "content": user_prompt})
        
        logger.info("构建完整消息列表:")
        logger.info("  total messages: %d", len(messages))
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            logger.info("    [%d] role=%s, content_length=%d", i, role, len(str(content)))
        
        logger.info("=== _answer_stream_from_lm_studio 开始流式返回 ===")
        stream_start_ts = time.monotonic()
        if runtime_client is not None:
            stream_result = runtime_client.chat_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=effective_max_tokens,
                include_reasoning=deep_think,
            )
        else:
            stream_result = self.kb.chat_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=effective_max_tokens,
            )

        def _instrument_stream(chunks: Sequence[str]) -> Iterator[str]:
            first_chunk_logged = False
            total_chunks = 0
            try:
                for piece in chunks:
                    total_chunks += 1
                    if not first_chunk_logged:
                        first_chunk_logged = True
                        logger.info(
                            "上游模型首包到达: latency_ms=%d",
                            int((time.monotonic() - stream_start_ts) * 1000),
                        )
                    yield piece
            finally:
                logger.info(
                    "上游模型流结束: total_chunks=%d elapsed_ms=%d",
                    total_chunks,
                    int((time.monotonic() - stream_start_ts) * 1000),
                )
        logger.info("流对象已返回，将由 SSE 实时转发到前端")
        return _instrument_stream(stream_result), None

    @staticmethod
    def _distance_to_similarity(distance: float) -> float:
        dist = float(distance)
        if dist < 0:
            dist = 0.0
        return 1.0 / (1.0 + dist)

    def _search_with_threshold_fallback(
        self,
        query: str,
        k: int,
        relevance_threshold: float | None,
    ) -> tuple[List[tuple[str, str, float]], float | None, bool]:
        effective_threshold = (
            None if relevance_threshold is None else float(relevance_threshold)
        )
        raw = self._filter_public_search_results(
            self.kb.search(query=query, k=k, relevance_threshold=effective_threshold)
        )
        threshold_relaxed = False
        if effective_threshold is not None and not raw:
            query_preview = query[:80] if len(query) > 80 else query
            logger.warning(
                "阈值检索返回空结果，回退为无阈值检索: query=%s threshold=%s",
                query_preview,
                effective_threshold,
            )
            fallback = self._filter_public_search_results(
                self.kb.search(query=query, k=k, relevance_threshold=None)
            )
            if fallback:
                raw = fallback
                threshold_relaxed = True
                effective_threshold = None
                logger.warning("阈值回退生效: fallback_results=%d", len(raw))
        return list(raw), effective_threshold, threshold_relaxed

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any] | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            pass
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _search_mcp_context(
        self,
        query: str,
        config_id: int | None = None,
    ) -> List[Dict[str, Any]]:
        search_query = str(query or "").strip()
        if config_id is not None:
            search_query = f"MCP 配置 {config_id} {search_query}".strip()
        raw = self.kb.search(query=search_query, k=8, relevance_threshold=None)
        results: List[Dict[str, Any]] = []
        for filename, text, distance in raw:
            if not self._is_internal_mcp_filename(filename):
                continue
            results.append(
                {
                    "filename": str(filename),
                    "text": str(text or ""),
                    "score": round(self._distance_to_similarity(float(distance)), 4),
                }
            )
        return results

    @staticmethod
    def _mcp_config_id_from_filename(filename: str | None) -> int | None:
        raw = str(filename or "")
        match = re.search(r"config_(\d+)\.md$", raw)
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    def _build_mcp_selection_messages(
        self,
        query: str,
        candidate_configs: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        candidate_lines = []
        for item in candidate_configs:
            candidate_lines.append(
                "\n".join(
                    [
                        f"config_id: {item.get('id')}",
                        f"name: {item.get('name') or ''}",
                        f"tool_name: {item.get('tool_name') or ''}",
                        f"transport_type: {item.get('transport_type') or 'http'}",
                        f"keyword_hints: {item.get('keyword_hints') or ''}",
                        f"description: {item.get('description') or ''}",
                        f"debug_hint: {item.get('debug_hint') or ''}",
                    ]
                )
            )
        return [
            {
                "role": "system",
                "content": (
                    "你是 MCP 路由器。根据用户问题，从候选 MCP 能力中判断是否应该调用。"
                    "只输出 JSON，不要解释。JSON 字段包含 should_call, reason, config_id。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户问题:\n{query}\n\n候选 MCP 能力:\n"
                    + "\n\n".join(candidate_lines)
                ),
            },
        ]

    def _select_mcp_config_for_chat(
        self,
        query: str,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = True,
    ) -> Dict[str, Any] | None:
        if not self._mcp_manager:
            return None
        context_items = self._search_mcp_context(query)
        candidate_configs: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for item in context_items:
            config_id = self._mcp_config_id_from_filename(item.get("filename"))
            if config_id is None or config_id in seen:
                continue
            config = self._mcp_manager.get_runtime_config(config_id=config_id, with_secret=False)
            if not config or not bool(config.get("is_active")):
                continue
            candidate_configs.append(config)
            seen.add(config_id)
            if len(candidate_configs) >= 4:
                break
        if not candidate_configs:
            return None
        if len(candidate_configs) == 1:
            return {"should_call": True, "reason": "命中唯一 MCP 配置候选", "config": candidate_configs[0]}
        try:
            runtime_client, model = self._resolve_runtime_model_config(
                model_config_id=model_config_id,
                model_config_name=model_config_name,
                use_default_model_config=use_default_model_config,
            )
            analysis_text = runtime_client.chat_once(
                messages=self._build_mcp_selection_messages(query, candidate_configs),
                model=model,
                temperature=0.1,
                max_tokens=600,
            )
            parsed = self._extract_json_object(str(analysis_text or "")) or {}
            should_call = self._parse_bool(parsed.get("should_call"), default=False)
            selected_id = parsed.get("config_id")
            if not should_call:
                return None
            try:
                selected_id = int(selected_id)
            except Exception:
                selected_id = int(candidate_configs[0].get("id") or 0)
            config = self._mcp_manager.get_runtime_config(config_id=selected_id, with_secret=False)
            if not config:
                return None
            return {
                "should_call": True,
                "reason": str(parsed.get("reason") or "模型判断应调用 MCP 能力"),
                "config": config,
            }
        except Exception as exc:
            logger.warning("MCP chat selection failed: %s", exc)
            return {"should_call": True, "reason": "候选检索命中，已回退选择首个 MCP 能力", "config": candidate_configs[0]}

    @staticmethod
    def _build_mcp_chat_result_context(mcp_execution: Dict[str, Any]) -> Dict[str, Any]:
        config = dict(mcp_execution.get("config") or {})
        dispatch = dict(mcp_execution.get("dispatch") or {})
        analysis = dict(mcp_execution.get("analysis") or {})
        response_json = dispatch.get("response_json")
        response_text = dispatch.get("response_text")
        if response_json is not None:
            tool_response = json.dumps(response_json, ensure_ascii=False, indent=2)
        else:
            tool_response = str(response_text or "")
        text = (
            "MCP 调度结果\n\n"
            f"能力名称: {config.get('name') or ''}\n"
            f"工具名: {config.get('tool_name') or ''}\n"
            f"调度原因: {analysis.get('reason') or ''}\n"
            f"是否成功: {'是' if mcp_execution.get('ok') else '否'}\n"
            f"请求信息: {json.dumps(dispatch.get('request') or {}, ensure_ascii=False, indent=2)}\n\n"
            f"响应结果:\n{tool_response}\n"
        )
        return {"filename": CHAT_MCP_SOURCE_FILENAME, "text": text, "score": 1.0}

    def _maybe_execute_mcp_for_chat(
        self,
        query: str,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = True,
    ) -> Dict[str, Any] | None:
        if not self._mcp_manager:
            return None
        selected = self._select_mcp_config_for_chat(
            query=query,
            model_config_id=model_config_id,
            model_config_name=model_config_name,
            use_default_model_config=use_default_model_config,
        )
        if not selected or not selected.get("config"):
            return None
        config = self._mcp_manager.get_runtime_config(config_id=int(selected["config"].get("id") or 0), with_secret=True)
        if not config:
            return None
        context_items = self._search_mcp_context(query, config_id=int(config.get("id") or 0))
        analysis = self._analyze_mcp_request(
            config=config,
            user_request=query,
            context_items=context_items,
            input_params=None,
            model_config_id=model_config_id,
            model_config_name=model_config_name,
            use_default_model_config=use_default_model_config,
        )
        if not self._parse_bool(analysis.get("should_call"), default=True):
            return None
        dispatch = self._mcp_manager.dispatch_config(config, analysis)
        return {
            "ok": bool(dispatch.get("ok")),
            "selection_reason": str(selected.get("reason") or ""),
            "config": self._mcp_manager._sanitize_config(config),
            "analysis": analysis,
            "context_documents": context_items,
            "dispatch": dispatch,
        }

    def _build_mcp_analysis_messages(
        self,
        config: Dict[str, Any],
        user_request: str,
        context_items: Sequence[Dict[str, Any]],
        input_params: Dict[str, Any] | None,
    ) -> List[Dict[str, str]]:
        context_text = self._build_context(context_items, max_chars=6000)
        config_payload = json.dumps(config.get("default_payload") or {}, ensure_ascii=False, indent=2)
        input_payload = json.dumps(input_params or {}, ensure_ascii=False, indent=2)
        system_prompt = (
            "你是 MCP 调度分析器。"
            "请根据提供的 MCP 能力配置和用户调试意图，输出一个 JSON 对象。"
            "不要输出 markdown，不要解释。"
            "JSON 可包含: should_call, reason, endpoint, http_method, headers, query_params, path_params, body。"
            "如果信息不足，也要尽量基于默认参数生成 body，并把不确定性写入 reason。"
        )
        user_prompt = (
            f"用户调试意图:\n{user_request}\n\n"
            f"目标能力名称: {config.get('name') or ''}\n"
            f"工具名: {config.get('tool_name') or ''}\n"
            f"基础地址: {config.get('base_url') or ''}\n"
            f"端点: {config.get('endpoint') or ''}\n"
            f"方法: {config.get('http_method') or 'POST'}\n"
            f"参数说明: {config.get('parameter_schema') or ''}\n"
            f"调试提示: {config.get('debug_hint') or ''}\n\n"
            f"默认参数(JSON):\n{config_payload}\n\n"
            f"前端补充输入(JSON):\n{input_payload}\n\n"
            f"知识库中检索到的 MCP 配置上下文:\n{context_text}\n"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _analyze_mcp_request(
        self,
        config: Dict[str, Any],
        user_request: str,
        context_items: Sequence[Dict[str, Any]],
        input_params: Dict[str, Any] | None = None,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = True,
    ) -> Dict[str, Any]:
        fallback = {
            "should_call": True,
            "reason": "使用默认参数进行调度",
            "endpoint": config.get("endpoint"),
            "http_method": config.get("http_method"),
            "headers": {},
            "query_params": {},
            "path_params": {},
            "body": dict(config.get("default_payload") or {}),
        }
        if isinstance(input_params, dict):
            fallback["body"].update(input_params)

        try:
            runtime_client, model = self._resolve_runtime_model_config(
                llm_model=None,
                model_config_id=model_config_id,
                model_config_name=model_config_name,
                use_default_model_config=use_default_model_config,
            )
            if runtime_client is None:
                return fallback
            analysis_text = runtime_client.chat_once(
                messages=self._build_mcp_analysis_messages(config, user_request, context_items, input_params),
                model=model,
                temperature=0.1,
                max_tokens=1200,
            )
            parsed = self._extract_json_object(str(analysis_text or ""))
            if not parsed:
                fallback["reason"] = "模型分析结果无法解析，已回退为默认参数调度"
                fallback["raw_analysis"] = str(analysis_text or "")
                return fallback
            if not isinstance(parsed.get("body"), dict):
                parsed["body"] = fallback["body"]
            else:
                merged_body = dict(fallback["body"])
                merged_body.update(parsed["body"])
                parsed["body"] = merged_body
            for key in ["headers", "query_params", "path_params"]:
                if not isinstance(parsed.get(key), dict):
                    parsed[key] = {}
            parsed.setdefault("should_call", True)
            parsed.setdefault("reason", "模型已根据知识库配置生成调度参数")
            parsed.setdefault("endpoint", config.get("endpoint"))
            parsed.setdefault("http_method", config.get("http_method"))
            parsed["raw_analysis"] = str(analysis_text or "")
            return parsed
        except Exception as exc:
            fallback["reason"] = f"模型分析失败，已回退为默认参数调度: {exc}"
            return fallback

    def debug_mcp(
        self,
        config_id: int,
        user_request: str,
        input_params: Dict[str, Any] | None = None,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = True,
    ) -> Dict[str, Any]:
        if not self._mcp_manager:
            raise RuntimeError("MCP 配置管理不可用（需要启用数据库后端）")
        config = self._mcp_manager.get_runtime_config(config_id=int(config_id), with_secret=True)
        if not config:
            raise ValueError(f"未找到 MCP 配置: {config_id}")
        if not bool(config.get("is_active")):
            raise ValueError("MCP 配置已停用，无法调试")

        context_items = self._search_mcp_context(user_request, config_id=int(config_id))
        analysis = self._analyze_mcp_request(
            config=config,
            user_request=user_request,
            context_items=context_items,
            input_params=input_params,
            model_config_id=model_config_id,
            model_config_name=model_config_name,
            use_default_model_config=use_default_model_config,
        )
        if not self._parse_bool(analysis.get("should_call"), default=True):
            return {
                "ok": False,
                "config": config,
                "analysis": analysis,
                "context_documents": context_items,
                "error": str(analysis.get("reason") or "模型判断当前不应调度该 MCP 能力"),
            }
        dispatch = self._mcp_manager.dispatch_config(config, analysis)
        return {
            "ok": bool(dispatch.get("ok")),
            "config": self._mcp_manager._sanitize_config(config),
            "analysis": analysis,
            "context_documents": context_items,
            "dispatch": dispatch,
        }

    def query(
        self,
        query: str,
        k: int = 2,
        relevance_threshold: float | None = None,
        llm_model: str | None = None,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = False,
        generate_answer: bool = True,
        temperature: float | None = 0.2,
        max_tokens: int | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        deep_think: bool = False,
        enable_mcp_auto: bool = False,
    ) -> Dict[str, Any]:
        if max_tokens is None:
            max_tokens = self._default_chat_max_tokens()
        
        logger.info("API query called: k=%s generate_answer=%s deep_think=%s", k, generate_answer, deep_think)
        logger.debug("查询详细参数:")
        logger.debug("  query: %s", query[:100] if len(query) > 100 else query)
        logger.debug("  k: %d", k)
        logger.debug("  relevance_threshold: %s", relevance_threshold)
        logger.debug("  llm_model: %s", llm_model)
        logger.debug("  temperature: %s", temperature)
        logger.debug("  max_tokens: %s", max_tokens)
        logger.debug("  user_id: %s", user_id)
        logger.debug("  session_id: %s", session_id)
        logger.debug("  deep_think: %s", deep_think)
        
        req = {
            "query": query,
            "k": int(k),
            "relevance_threshold": (
                None if relevance_threshold is None else float(relevance_threshold)
            ),
            "llm_model": llm_model,
            "model_config_id": model_config_id,
            "model_config_name": model_config_name,
            "use_default_model_config": bool(use_default_model_config),
            "generate_answer": bool(generate_answer),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "user_id": user_id,
            "session_id": session_id,
            "deep_think": bool(deep_think),
            "enable_mcp_auto": bool(enable_mcp_auto),
        }
        try:
            logger.debug("开始执行知识库检索...")
            raw, effective_threshold, threshold_relaxed = self._search_with_threshold_fallback(
                query=query,
                k=k,
                relevance_threshold=relevance_threshold,
            )
            logger.debug("检索到 %d 个原始结果", len(raw))
            min_similarity = self._min_source_similarity()
            logger.debug("来源最小相似度阈值: %s", min_similarity)
            
            ranked_results = []
            result_items = []
            for idx, (fn, text, distance_raw) in enumerate(raw):
                logger.debug("处理检索结果 #%d: filename=%s, distance=%.4f", idx, fn, distance_raw)
                distance = max(0.0, float(distance_raw))
                similarity = self._distance_to_similarity(distance)
                if similarity < min_similarity:
                    logger.debug(
                        "过滤低相似度结果: filename=%s similarity=%.4f < min_source_similarity=%.4f",
                        fn,
                        similarity,
                        min_similarity,
                    )
                    continue
                chunk_text = str(text or "")
                ranked_results.append({"filename": fn, "text": chunk_text, "score": similarity})
                result_items.append(
                    {
                        "distance": round(float(distance), 4),
                        "filename": str(fn),
                        "similarity": round(float(similarity), 4),
                        "text": chunk_text,
                        "preview_text": chunk_text[:240],
                    }
                )
            mcp_execution = None
            if enable_mcp_auto:
                mcp_execution = self._maybe_execute_mcp_for_chat(
                    query=query,
                    model_config_id=model_config_id,
                    model_config_name=model_config_name,
                    use_default_model_config=use_default_model_config,
                )
                if mcp_execution:
                    ranked_results.insert(0, self._build_mcp_chat_result_context(mcp_execution))
            answer = ""
            finish_reason = "stop"
            is_complete = True
            logger.debug("加载聊天上下文...")
            history_messages = self._load_chat_context(user_id, session_id)
            logger.debug("加载了 %d 条历史消息", len(history_messages))
            
            logger.debug("构建聊天提示词...")
            system_prompt, user_prompt = self._build_chat_prompts(query, ranked_results, deep_think=deep_think)
            logger.debug("系统提示词长度: %d, 用户提示词长度: %d", len(system_prompt), len(user_prompt))
            
            if generate_answer:
                logger.debug("开始生成答案，使用 %d 个检索结果", len(ranked_results))
                answer, thinking, thinking_summary = self._answer_from_lm_studio(
                    question=query,
                    results=ranked_results,
                    llm_model=llm_model,
                    model_config_id=model_config_id,
                    model_config_name=model_config_name,
                    use_default_model_config=use_default_model_config,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    history_messages=history_messages,
                    deep_think=deep_think,
                )
                logger.debug("答案生成完成，长度: %d", len(answer))
                if thinking:
                    logger.debug("思考内容长度: %d", len(thinking))
                if thinking_summary:
                    logger.debug("思考摘要长度: %d", len(thinking_summary))
            else:
                logger.debug("跳过答案生成（generate_answer=False）")
                finish_reason = "not_requested"
                thinking = None
                thinking_summary = None
            messages = [
                {"role": "system", "content": system_prompt},
                *history_messages,
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": answer},
            ]
            resp: Dict[str, Any] = {
                "answer": answer,
                "finish_reason": finish_reason,
                "is_complete": bool(is_complete),
                "results": result_items,
                "session_id": session_id,
                "user_id": user_id,
                "thinking": thinking,
                "thinking_summary": thinking_summary,
                "relevance_threshold": effective_threshold,
                "threshold_relaxed": bool(threshold_relaxed),
                "mcp_execution": mcp_execution,
                "messages": messages,
            }
            self._append_history("query", req, resp, thinking_summary=thinking_summary)
            logger.info("API query completed: results=%s", len(result_items))
            return resp
        except Exception as exc:
            self._append_history("query", req, {"ok": False}, error=str(exc))
            logger.exception("API query failed")
            raise

    def query_stream(
        self,
        query: str,
        k: int = 2,
        relevance_threshold: float | None = None,
        llm_model: str | None = None,
        model_config_id: int | None = None,
        model_config_name: str | None = None,
        use_default_model_config: bool = False,
        generate_answer: bool = True,
        temperature: float | None = 0.2,
        max_tokens: int | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        deep_think: bool = False,
        enable_mcp_auto: bool = False,
    ) -> Dict[str, Any]:
        if max_tokens is None:
            max_tokens = self._default_chat_max_tokens()
        req = {
            "query": query,
            "k": int(k),
            "relevance_threshold": (
                None if relevance_threshold is None else float(relevance_threshold)
            ),
            "llm_model": llm_model,
            "model_config_id": model_config_id,
            "model_config_name": model_config_name,
            "use_default_model_config": bool(use_default_model_config),
            "generate_answer": bool(generate_answer),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "user_id": user_id,
            "session_id": session_id,
            "deep_think": bool(deep_think),
            "enable_mcp_auto": bool(enable_mcp_auto),
        }
        raw, effective_threshold, threshold_relaxed = self._search_with_threshold_fallback(
            query=query,
            k=k,
            relevance_threshold=relevance_threshold,
        )
        min_similarity = self._min_source_similarity()
        ranked_results = []
        result_items = []
        for fn, text, distance_raw in raw:
            distance = max(0.0, float(distance_raw))
            similarity = self._distance_to_similarity(distance)
            if similarity < min_similarity:
                continue
            chunk_text = str(text or "")
            ranked_results.append({"filename": fn, "text": chunk_text, "score": similarity})
            result_items.append(
                {
                    "distance": round(float(distance), 4),
                    "filename": str(fn),
                    "similarity": round(float(similarity), 4),
                    "text": chunk_text,
                    "preview_text": chunk_text[:240],
                }
            )

        mcp_execution = None
        if enable_mcp_auto:
            mcp_execution = self._maybe_execute_mcp_for_chat(
                query=query,
                model_config_id=model_config_id,
                model_config_name=model_config_name,
                use_default_model_config=use_default_model_config,
            )
            if mcp_execution:
                ranked_results.insert(0, self._build_mcp_chat_result_context(mcp_execution))

        stream = []
        history_messages = self._load_chat_context(user_id, session_id)
        logger.info("上下文=%s", history_messages)
        system_prompt, user_prompt = self._build_chat_prompts(query, ranked_results, deep_think=deep_think)
        if generate_answer:
            stream, thinking_summary = self._answer_stream_from_lm_studio(
                question=query,
                results=ranked_results,
                llm_model=llm_model,
                model_config_id=model_config_id,
                model_config_name=model_config_name,
                use_default_model_config=use_default_model_config,
                temperature=temperature,
                max_tokens=max_tokens,
                history_messages=history_messages,
                deep_think=deep_think,
            )
        else:
            thinking_summary = None
        return {
            "req": req,
            "results": result_items,
            "stream": stream,
            "history_messages": history_messages,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "thinking_summary": thinking_summary,
            "relevance_threshold": effective_threshold,
            "threshold_relaxed": bool(threshold_relaxed),
            "mcp_execution": mcp_execution,
        }

    def add_document(self, filename: str, text: str) -> Dict[str, Any]:
        try:
            chunks = self.kb.add_document(filename, text)
            resp = {"ok": True, "chunks_added": int(chunks)}
            return resp
        except Exception as exc:
            raise

    def add_file(self, file_path: str) -> Dict[str, Any]:
        try:
            chunks = self.kb.add_text_file(file_path)
            resp = {"ok": True, "chunks_added": int(chunks)}
            return resp
        except Exception as exc:
            raise

    def add_uploaded_file(
        self, filename: str, content: bytes, encoding: str | None = None
    ) -> Dict[str, Any]:
        try:
            chunks = self.kb.add_uploaded_file(filename=filename, content=content, encoding=encoding)
            resp = {"ok": True, "chunks_added": int(chunks)}
            return resp
        except Exception as exc:
            raise

    def add_uploaded_files(
        self, files: Sequence[Dict[str, Any]], encoding: str | None = None
    ) -> Dict[str, Any]:
        try:
            total_chunks = 0
            for item in files:
                filename = str(item.get("filename") or "").strip()
                if not filename:
                    continue
                total_chunks += self.kb.add_uploaded_file(
                    filename=filename,
                    content=item.get("content") or b"",
                    encoding=encoding,
                )
            resp = {"ok": True, "chunks_added": int(total_chunks)}
            return resp
        except Exception as exc:
            raise

    def list_chunks(
        self,
        page_index: int = 1,
        page_size: int = 20,
        filename: str | None = None,
        query: str | None = None,
    ) -> Dict[str, Any]:
        try:
            try:
                from ..kb.documents import list_chunks as kb_list_chunks
            except ImportError:  # pragma: no cover
                from kb.documents import list_chunks as kb_list_chunks
            return kb_list_chunks(
                self.kb,
                page_index=page_index,
                page_size=page_size,
                filename=filename,
                query=query,
                is_internal_filename=self._is_internal_mcp_filename,
            )
        except Exception:
            raise

    def list_documents(self) -> Dict[str, Any]:
        try:
            from ..kb.documents import list_documents as kb_list_documents
        except ImportError:  # pragma: no cover
            from kb.documents import list_documents as kb_list_documents
        return kb_list_documents(
            self.kb,
            is_internal_filename=self._is_internal_mcp_filename,
        )

    def update_chunk(self, chunk_id: int, text: str) -> Dict[str, Any]:
        try:
            self.kb.update_chunk(chunk_id=chunk_id, text=text)
            return {"ok": True}
        except Exception:
            raise

    def delete_chunk(self, chunk_id: int) -> Dict[str, Any]:
        try:
            self.kb.delete_chunk(chunk_id=chunk_id)
            return {"ok": True}
        except Exception:
            raise

    def rebuild_chunks_for_filename(self, filename: str) -> Dict[str, Any]:
        try:
            if self._is_internal_mcp_filename(filename):
                raise ValueError("内部 MCP 配置文档不支持重建分片")
            chunks = self.kb.rebuild_chunks_for_filename(filename)
            return {"ok": True, "chunks_added": int(chunks)}
        except Exception:
            raise

    def remove_document(self, filename: str) -> Dict[str, Any]:
        try:
            if self._is_internal_mcp_filename(filename):
                raise ValueError("内部 MCP 配置文档不可通过知识库页面删除")
            removed = self.kb.remove_document(filename)
            return {"ok": True, "chunks_removed": int(removed)}
        except Exception:
            raise

    def get_knowledge_base_stats(self) -> Dict[str, Any]:
        stats = self.kb.stats()
        resp = {"ok": True, "stats": stats}
        return resp

    def clear_knowledge_base(self) -> Dict[str, Any]:
        try:
            self.kb.clear()
            self._resync_mcp_documents()
            resp = {"ok": True}
            return resp
        except Exception as exc:
            raise

    def get_history(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        return self._history_store.get(limit=limit, action=action)

    def get_history_sessions(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        """按session分组获取历史记录"""
        return self._history_store.get_by_sessions(limit=limit, action=action)

    def clear_history(self) -> int:
        return self._history_store.clear()

    def delete_history(self, item_id: int) -> int:
        return self._history_store.delete(item_id)

    def delete_session(self, session_id: str) -> int:
        """删除整个session及其所有消息"""
        if hasattr(self._history_store, 'delete_session'):
            return self._history_store.delete_session(session_id)
        else:
            # 如果是内存存储，需要删除所有属于该session的消息
            # 这里暂不实现，因为主要针对数据库存储
            raise NotImplementedError("当前存储后端不支持删除整段会话")


class API(KnowledgeBaseApi):
    pass


class HttpApiServer:

    def __init__(self, api: KnowledgeBaseApi, host: str = "127.0.0.1", port: int = 5000):
        self.api = api
        self.host = host
        self.port = int(port)
        self._server = ThreadingHTTPServer((self.host, self.port), self._build_handler())

    def _build_handler(self):
        api = self.api

        class Handler(BaseHTTPRequestHandler):
            server_version = "KnowledgeBaseHTTP/1.0"

            @staticmethod
            def _infer_total(payload: Any) -> int:
                if isinstance(payload, dict):
                    if isinstance(payload.get("total"), int):
                        return int(payload["total"])
                    if isinstance(payload.get("count"), int):
                        return int(payload["count"])
                    if isinstance(payload.get("results"), list):
                        return len(payload["results"])
                    if isinstance(payload.get("documents"), list):
                        return len(payload["documents"])
                    if isinstance(payload.get("history"), list):
                        return len(payload["history"])
                    if isinstance(payload.get("chunks_added"), int):
                        return int(payload["chunks_added"])
                    if isinstance(payload.get("chunks_removed"), int):
                        return int(payload["chunks_removed"])
                    if isinstance(payload.get("removed"), int):
                        return int(payload["removed"])
                    return 1 if payload else 0
                if isinstance(payload, list):
                    return len(payload)
                return 1 if payload is not None else 0

            def _wrap_payload(self, status: int, payload: Any, page_index: int = 1) -> Dict[str, Any]:
                if (
                    isinstance(payload, dict)
                    and "total" in payload
                    and "code" in payload
                    and "data" in payload
                    and "pageIndex" in payload
                ):
                    return payload
                if status >= 400:
                    message = ""
                    if isinstance(payload, dict):
                        message = str(payload.get("error") or payload.get("message") or "")
                    elif payload is not None:
                        message = str(payload)
                    data: Any = None if not message else {"error": message}
                    return {
                        "total": 0,
                        "code": int(status),
                        "data": data,
                        "pageIndex": int(page_index),
                    }
                return {
                    "total": self._infer_total(payload),
                    "code": int(status),
                    "data": payload,
                    "pageIndex": int(page_index),
                }

            def _cors_headers(self) -> None:
                """开发态 Vite(5173) 直连 SSE 时需要；生产同源也不碍事。"""
                origin = str(self.headers.get("Origin") or "").strip()
                if origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Access-Control-Allow-Credentials", "true")
                    self.send_header("Vary", "Origin")
                else:
                    self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, Accept, Cache-Control, X-Requested-With",
                )
                self.send_header(
                    "Access-Control-Allow-Methods",
                    "GET, POST, PUT, DELETE, OPTIONS",
                )

            def _send_json(self, status: int, payload: Any, page_index: int = 1) -> None:
                wrapped = self._wrap_payload(status=status, payload=payload, page_index=page_index)
                body = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def _send_sse_headers(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                # SSE 必须关 keep-alive，否则前端 reader 会一直等到超时
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self._cors_headers()
                self.end_headers()

            def _send_sse(self, event: str, payload: Dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=False)
                message = f"event: {event}\ndata: {data}\n\n".encode("utf-8")
                self.wfile.write(message)
                self.wfile.flush()

            def do_OPTIONS(self):  # noqa: N802
                self.send_response(204)
                self._cors_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()

            @staticmethod
            def _guess_content_type(file_path: Path) -> str:
                suffix = file_path.suffix.lower()
                if suffix == ".md":
                    return "text/markdown; charset=utf-8"
                if suffix == ".js":
                    return "application/javascript; charset=utf-8"
                if suffix == ".css":
                    return "text/css; charset=utf-8"

                guessed, _ = mimetypes.guess_type(str(file_path))
                if not guessed:
                    return "application/octet-stream"
                if guessed.startswith("text/") or guessed in {
                    "application/json",
                    "application/javascript",
                    "image/svg+xml",
                }:
                    return guessed + "; charset=utf-8"
                return guessed

            @staticmethod
            def _resolve_static_file(base_dir: Path, relative_path: str) -> Path | None:
                if not base_dir.exists():
                    return None
                base = base_dir.resolve()
                rel = str(relative_path or "").replace("\\", "/").lstrip("/")
                if not rel:
                    return None
                candidate = (base / rel).resolve()
                try:
                    candidate.relative_to(base)
                except ValueError:
                    return None
                if not candidate.is_file():
                    return None
                return candidate

            def _serve_static(self, base_dir: Path, relative_path: str) -> bool:
                target = self._resolve_static_file(base_dir, relative_path)
                if target is None:
                    return False
                try:
                    body = target.read_bytes()
                except Exception:
                    return False
                self._send_bytes(200, body, self._guess_content_type(target))
                return True

            def _ok(self, payload: Any, page_index: int = 1) -> None:
                self._send_json(200, payload, page_index=page_index)

            def _bad_request(self, message: str, page_index: int = 1) -> None:
                self._send_json(400, {"error": message}, page_index=page_index)

            def _not_found(self, page_index: int = 1) -> None:
                self._send_json(404, {"error": "资源不存在"}, page_index=page_index)

            def _internal_error(self, exc: Exception, page_index: int = 1) -> None:
                logger.exception("HTTP internal error: %s", exc)
                self._send_json(500, {"error": str(exc)}, page_index=page_index)

            def _read_body_bytes(self) -> bytes:
                length_raw = self.headers.get("Content-Length", "").strip()
                if not length_raw:
                    return b""
                try:
                    length = int(length_raw)
                except Exception:
                    raise ValueError("无效的 Content-Length")
                return self.rfile.read(max(0, length))

            def _read_json(self) -> Dict[str, Any]:
                raw = self._read_body_bytes()
                if not raw:
                    return {}
                try:
                    obj = json.loads(raw.decode("utf-8"))
                except Exception as exc:
                    raise ValueError("JSON 请求体格式无效") from exc
                if not isinstance(obj, dict):
                    raise ValueError("JSON 请求体必须是对象")
                return obj

            def _read_multipart_file(self, field_name: str = "file") -> Dict[str, Any]:
                content_type = self.headers.get("Content-Type", "")
                if "multipart/form-data" not in content_type.lower():
                    raise ValueError("Content-Type 必须为 multipart/form-data")

                raw = self._read_body_bytes()
                if not raw:
                    raise ValueError("请求体为空")

                header = (
                    f"Content-Type: {content_type}\r\n"
                    "MIME-Version: 1.0\r\n\r\n"
                ).encode("utf-8")
                message = BytesParser(policy=default).parsebytes(header + raw)
                if not message.is_multipart():
                    raise ValueError("multipart 请求体格式无效")

                form: Dict[str, str] = {}
                uploaded: Dict[str, Any] | None = None
                for part in message.iter_parts():
                    disposition = part.get("Content-Disposition", "")
                    if "form-data" not in disposition:
                        continue
                    name = part.get_param("name", header="content-disposition")
                    if not name:
                        continue

                    filename = part.get_filename()
                    payload = part.get_payload(decode=True) or b""
                    if filename is not None:
                        if name == field_name:
                            uploaded = {"filename": filename, "content": payload}
                        continue

                    charset = part.get_content_charset() or "utf-8"
                    try:
                        form[name] = payload.decode(charset).strip()
                    except Exception:
                        form[name] = payload.decode("utf-8", errors="replace").strip()

                if uploaded is None:
                    raise ValueError(f"缺少必填字段: {field_name}")

                uploaded["form"] = form
                return uploaded

            def _read_multipart_files(self, field_name: str = "files") -> Dict[str, Any]:
                content_type = self.headers.get("Content-Type", "")
                if "multipart/form-data" not in content_type.lower():
                    raise ValueError("Content-Type 必须为 multipart/form-data")

                raw = self._read_body_bytes()
                if not raw:
                    raise ValueError("请求体为空")

                header = (
                    f"Content-Type: {content_type}\r\n"
                    "MIME-Version: 1.0\r\n\r\n"
                ).encode("utf-8")
                message = BytesParser(policy=default).parsebytes(header + raw)
                if not message.is_multipart():
                    raise ValueError("multipart 请求体格式无效")

                form: Dict[str, str] = {}
                uploads: List[Dict[str, Any]] = []
                for part in message.iter_parts():
                    disposition = part.get("Content-Disposition", "")
                    if "form-data" not in disposition:
                        continue
                    name = part.get_param("name", header="content-disposition")
                    if not name:
                        continue

                    filename = part.get_filename()
                    payload = part.get_payload(decode=True) or b""
                    if filename is not None:
                        if name == field_name:
                            uploads.append({"filename": filename, "content": payload})
                        continue

                    charset = part.get_content_charset() or "utf-8"
                    try:
                        form[name] = payload.decode(charset).strip()
                    except Exception:
                        form[name] = payload.decode("utf-8", errors="replace").strip()

                if not uploads:
                    raise ValueError(f"缺少必填字段: {field_name}")

                return {"files": uploads, "form": form}

            def _parse_query_params(self) -> Dict[str, List[str]]:
                parsed = urlparse(self.path)
                return parse_qs(parsed.query, keep_blank_values=True)

            def _get_param_value(self, params: Dict[str, List[str]], key: str, default: str = "") -> str:
                """安全地从查询参数字典中获取值"""
                if not isinstance(params, dict):
                    return default
                values = params.get(key)
                if not values or not isinstance(values, list) or len(values) == 0:
                    return default
                return values[-1] if values[-1] is not None else default

            @staticmethod
            def _to_positive_int(value: Any, default: int = 1) -> int:
                try:
                    num = int(value)
                except Exception:
                    return int(default)
                return num if num > 0 else int(default)

            def _page_index_from_params(self, params: Dict[str, List[str]]) -> int:
                raw = self._get_param_value(params, "pageIndex", "1")
                return self._to_positive_int(raw, default=1)

            def _page_index_from_body(self, body: Dict[str, Any]) -> int:
                if not isinstance(body, dict):
                    return 1
                raw = body.get("pageIndex", 1)
                return self._to_positive_int(raw, default=1)

            def _path(self) -> str:
                return urlparse(self.path).path

            def _dispatch_api_get(self, logical: str) -> bool:
                """按去掉 /api 后的逻辑路径分发 GET；已处理返回 True。"""
                if logical == "/health":
                    self._ok({"ok": True, "message": "服务正常"})
                    return True
                if handle_get_session(self, api, logical):
                    return True
                if handle_get_query(self, api, logical):
                    return True
                if handle_get_stats(self, api, logical):
                    return True
                if handle_get_kb(self, api, logical):
                    return True
                if handle_get_history(self, api, logical):
                    return True
                if handle_get_model(self, api, logical):
                    return True
                if handle_get_mcp(self, api, logical):
                    return True
                return False

            def _dispatch_api_post(self, logical: str) -> bool:
                if logical in {"/kb/file", "/kb/files"}:
                    if handle_post_kb(self, api, logical, body=None):
                        return True
                body = self._read_json()
                if handle_post_session(self, api, logical, body):
                    return True
                if handle_post_query(self, api, logical, body):
                    return True
                if handle_post_kb(self, api, logical, body=body):
                    return True
                if handle_post_model(self, api, logical, body):
                    return True
                if handle_post_mcp(self, api, logical, body):
                    return True
                return False

            @staticmethod
            def _http_access_log_enabled() -> bool:
                raw = str(os.getenv("KB_HTTP_ACCESS_LOG", "")).strip().lower()
                return raw in {"1", "true", "yes", "on"}

            def log_message(self, fmt: str, *args):  # noqa: D401
                # Keep default behavior quiet, but allow opt-in access logs.
                if not self._http_access_log_enabled():
                    return
                try:
                    message = (fmt % args) if args else fmt
                except Exception:
                    message = fmt
                client_ip = "-"
                if getattr(self, "client_address", None):
                    client_ip = str(self.client_address[0])
                logger.info("HTTP access: client=%s %s", client_ip, message)

            def do_GET(self):  # noqa: N802
                try:
                    api.request_started()
                    path = self._path()
                    # 遗留静态台（默认关闭；KB_SERVE_LEGACY_WEB=1 时启用）
                    if path.startswith("/legacy-ui"):
                        if not legacy_web_enabled():
                            self._bad_request(
                                "遗留 web UI 已归档。请使用 frontend/ 构建产物（/），"
                                "或设置环境变量 KB_SERVE_LEGACY_WEB=1 临时启用 /legacy-ui/"
                            )
                            return
                        if path in {"/legacy-ui", "/legacy-ui/"}:
                            if self._serve_static(LEGACY_WEB_DIR, "index.html"):
                                return
                            self._internal_error(
                                FileNotFoundError("未找到遗留入口: archive/web/index.html")
                            )
                            return
                        rel = path[len("/legacy-ui/") :]
                        if self._serve_static(LEGACY_WEB_DIR, rel):
                            return
                        self._not_found()
                        return
                    # 兼容旧书签：/ui → Vue 控制台
                    if path in {"/ui", "/ui/"} or path.startswith("/ui/"):
                        path = "/" if path in {"/ui", "/ui/"} else "/" + path[len("/ui/") :]
                    if path.startswith("/assets/"):
                        rel = path[len("/assets/") :]
                        if self._serve_static(ASSETS_DIR, rel):
                            return
                        self._not_found()
                        return
                    # API 文档已是 Vue 路由：禁止再吐独立 HTML（含 docs/API.html）
                    if path in {
                        "/api-docs",
                        "/api-docs/",
                        "/api-docs.html",
                        "/docs",
                        "/docs/",
                        "/docs/API.html",
                    }:
                        if not FRONTEND_DIST.is_dir():
                            self._internal_error(
                                FileNotFoundError(
                                    "未找到 frontend/dist。请先执行: cd frontend && npm run build"
                                )
                            )
                            return
                        if path in {"/api-docs", "/api-docs/"}:
                            if self._serve_static(FRONTEND_DIST, "index.html"):
                                return
                            self._not_found()
                            return
                        self.send_response(302)
                        self.send_header("Location", "/api-docs")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if path.startswith("/docs/"):
                        # 其它 /docs/* 仍可静态提供；缺失则回 Vue 文档页
                        rel = path[len("/docs/") :]
                        if self._serve_static(DOCS_DIR, rel):
                            return
                        self.send_response(302)
                        self.send_header("Location", "/api-docs")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    # 探活：保留裸 /health，同时支持 /api/health
                    if path == "/health":
                        self._ok({"ok": True, "message": "服务正常"})
                        return

                    logical = strip_api_prefix(path)
                    if logical is not None:
                        if self._dispatch_api_get(logical):
                            return
                        self._not_found()
                        return

                    # 默认：Vue 构建产物（frontend/dist）+ SPA fallback
                    if not is_api_or_docs_path(path):
                        if not FRONTEND_DIST.is_dir():
                            self._internal_error(
                                FileNotFoundError(
                                    "未找到 frontend/dist。请先执行: cd frontend && npm run build"
                                )
                            )
                            return
                        rel = "index.html" if path in {"/", ""} else path.lstrip("/")
                        if self._serve_static(FRONTEND_DIST, rel):
                            return
                        if should_spa_fallback(path) and self._serve_static(
                            FRONTEND_DIST, "index.html"
                        ):
                            return
                        self._not_found()
                        return
                    self._not_found()
                except Exception as exc:
                    self._internal_error(exc)
                finally:
                    api.request_finished()
                    api.maybe_release_gpu()

            def do_POST(self):  # noqa: N802
                try:
                    api.request_started()
                    path = self._path()
                    logical = strip_api_prefix(path)
                    if logical is None:
                        self._bad_request("接口须使用 /api 前缀，例如 POST /api/query")
                        return
                    if self._dispatch_api_post(logical):
                        return
                    self._not_found()
                except ValueError as exc:
                    self._bad_request(str(exc))
                except Exception as exc:
                    self._internal_error(exc)
                finally:
                    api.request_finished()
                    api.maybe_release_gpu()

            def do_PUT(self):  # noqa: N802
                try:
                    api.request_started()
                    path = self._path()
                    logical = strip_api_prefix(path)
                    if logical is None:
                        self._bad_request("接口须使用 /api 前缀，例如 PUT /api/model/config/{id}")
                        return
                    if handle_put_kb(self, api, logical):
                        return
                    if handle_put_model(self, api, logical):
                        return
                    if handle_put_mcp(self, api, logical):
                        return
                    self._not_found()
                except ValueError as exc:
                    self._bad_request(str(exc))
                except Exception as exc:
                    self._internal_error(exc)
                finally:
                    api.request_finished()
                    api.maybe_release_gpu()

            def do_DELETE(self):  # noqa: N802
                try:
                    api.request_started()
                    path = self._path()
                    logical = strip_api_prefix(path)
                    if logical is None:
                        self._bad_request("接口须使用 /api 前缀，例如 DELETE /api/kb/document/{name}")
                        return
                    if handle_delete_kb(self, api, logical):
                        return
                    if handle_delete_history(self, api, logical):
                        return
                    if handle_delete_session(self, api, logical):
                        return
                    if handle_delete_model(self, api, logical):
                        return
                    if handle_delete_mcp(self, api, logical):
                        return
                    self._not_found()
                except Exception as exc:
                    self._internal_error(exc)
                finally:
                    api.request_finished()
                    api.maybe_release_gpu()

        return Handler

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
