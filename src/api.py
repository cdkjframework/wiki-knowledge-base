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
    from .store.db.history_store import DatabaseHistoryStore
    from .store.db.connection import DatabaseConnection
    from .store.interfaces import HistoryStore, SessionIdStore
    from .store.memory_store import InMemoryHistoryStore, InMemorySessionIdStore
    from .store.redis.session_store import RedisSessionIdStore
    from .model_config_manager import ModelConfigManager
except ImportError:  # pragma: no cover
    from store.db.history_store import DatabaseHistoryStore
    from store.db.connection import DatabaseConnection
    from store.interfaces import HistoryStore, SessionIdStore
    from store.memory_store import InMemoryHistoryStore, InMemorySessionIdStore
    from store.redis.session_store import RedisSessionIdStore
    from model_config_manager import ModelConfigManager

try:
    from .knowledge_base import KnowledgeBase
except ImportError:  # pragma: no cover
    from knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


def _project_root_from_config(config_path: Path) -> Path | None:
    if not config_path.exists():
        return None
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(cfg, dict):
        return None
    raw = str(cfg.get("KB_PROJECT_ROOT") or cfg.get("B_PROJECT_ROOT") or "").strip()
    if not raw:
        return None
    root = Path(raw)
    if not root.is_absolute():
        root = (config_path.parent / root).resolve()
    else:
        root = root.expanduser().resolve()
    return root if root.exists() else None


def _resolve_project_root() -> Path:
    env_root = str(os.getenv("KB_PROJECT_ROOT") or "").strip()
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    cwd = Path.cwd().resolve()
    cfg_root = _project_root_from_config(cwd / "config.json")
    if cfg_root is not None:
        return cfg_root
    if (cwd / "config.json").exists():
        return cwd

    pkg_cfg = Path(__file__).resolve().parent.parent / "config.json"
    cfg_root = _project_root_from_config(pkg_cfg)
    if cfg_root is not None:
        return cfg_root

    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()
WEB_DIR = PROJECT_ROOT / "web"
DOCS_DIR = PROJECT_ROOT / "docs"
ASSETS_DIR = PROJECT_ROOT / "assets"

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
    def _finalize_stream_split_state(state: Dict[str, Any]) -> tuple[str, str, str | None]:
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

        # 回退规则：无 think 标签时尝试按“Final Answer/最终答案”分段
        if not thinking and not bool(state.get("seen_think_tag", False)):
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
        cfg_path = PROJECT_ROOT / "config.json"
        if not cfg_path.exists():
            return {}
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

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
        cfg_path = PROJECT_ROOT / "config.json"
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
        cfg_path = PROJECT_ROOT / "config.json"
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
        deep_think: bool = True,
        model_type_override: str | None = None,
    ) -> str:
        """根据 model_type 应用不同的深度思考策略"""
        if not deep_think:
            return system_prompt
        
        model_type = str(model_type_override or self._get_model_type()).strip().lower()
        logger.info(
            "[THINK_STRATEGY] override=%s resolved_model_type=%s deep_think=%s",
            model_type_override,
            model_type,
            deep_think,
        )
        
        if ("gpt" in model_type) or (model_type in {"openai", "chatgpt"}):
            # GPT 模型：在系统提示词前添加推理级别
            system_prompt = "Reasoning: high\n" + system_prompt
            logger.info("应用 GPT 深度思考策略：添加 Reasoning: high")
        
        elif ("qwen" in model_type) or (model_type in {"dashscope"}):
            # Qwen 模型：在系统提示词中添加思考引导
            # 由于使用 LM Studio，无法直接设置 enable_thinking 参数
            # 通过在系统提示词中明确要求输出思考过程
            qwen_think_prompt = (
                "\n\n请在回答前进行深度思考：\n"
                "1. 仅将真实思考内容放入 <think>...</think>，不要复述提示词，不要解释标签规则，不要讨论输出格式。\n"
                "2. 思考结束后直接给出最终答案。\n"
                "3. 思考过程应包含：问题分析、知识检索、逻辑推理、结论验证。\n"
                "4. 在思考末尾用 <thinking_summary>...</thinking_summary> 给出一句简短摘要。"
            )
            system_prompt += qwen_think_prompt
            logger.info("应用 Qwen 深度思考策略：添加 <think> 标签引导")
        
        elif "deepseek" in model_type:
            # DeepSeek 模型：添加明确的逐步推理要求
            deepseek_think_prompt = (
                "\n\n请进行深度逐步推理：\n"
                "1. 仔细分析问题的核心要点\n"
                "2. 列举所有相关的知识和信息\n"
                "3. 逐步推导，展示每一步的思考过程\n"
                "4. 验证推理的逻辑性和一致性\n"
                "5. 在充分思考后给出最终答案\n"
                "请在回答中明确标注【思考过程】和【最终答案】两个部分，"
                "并在末尾用 <thinking_summary>...</thinking_summary> 标签给出思考摘要。"
            )
            system_prompt += deepseek_think_prompt
            logger.info("应用 DeepSeek 深度思考策略：添加逐步推理引导")
        
        else:
            # 默认策略（兼容旧版本）
            default_think_prompt = (
                "\n\n请进行深度思考和分析：\n"
                "1. 仔细分析问题的多个方面\n"
                "2. 考虑相关的背景信息和上下文\n"
                "3. 提供全面和深层的解释\n"
                "4. 如有必要，说明你的推理过程\n\n"
                "请在答案末尾追加思考摘要，使用如下标签包裹：\n"
                "<thinking_summary>...简要思考摘要...</thinking_summary>"
            )
            system_prompt += default_think_prompt
            logger.info("应用默认深度思考策略")
        
        return system_prompt

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
        self, question: str, results: Sequence[Dict[str, Any]]
    ) -> tuple[str, str]:
        context = self._build_context(results)
        if not context:
            return (
                self._base_system_prompt(with_context=False),
                f"用户问题：{question}\n\n当前未检索到相关知识库内容。请使用简体中文明确说明根据当前知识库无法确定答案。",
            )
        system_prompt = self._base_system_prompt(with_context=True)
        user_prompt = (
            f"用户问题：{question}\n\n"
            f"知识库上下文：\n{context}\n\n"
            "请基于以上内容，用简体中文给出准确、简洁、可核对的回答。"
        )
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
        deep_think: bool = True,
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
        system_prompt, user_prompt = self._build_chat_prompts(question, results)
        
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
        deep_think: bool = True,
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
        system_prompt, user_prompt = self._build_chat_prompts(question, results)
        
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
        raw = self.kb.search(query=query, k=k, relevance_threshold=effective_threshold)
        threshold_relaxed = False
        if effective_threshold is not None and not raw:
            query_preview = query[:80] if len(query) > 80 else query
            logger.warning(
                "阈值检索返回空结果，回退为无阈值检索: query=%s threshold=%s",
                query_preview,
                effective_threshold,
            )
            fallback = self.kb.search(query=query, k=k, relevance_threshold=None)
            if fallback:
                raw = fallback
                threshold_relaxed = True
                effective_threshold = None
                logger.warning("阈值回退生效: fallback_results=%d", len(raw))
        return list(raw), effective_threshold, threshold_relaxed

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
        deep_think: bool = True,
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
            answer = ""
            finish_reason = "stop"
            is_complete = True
            logger.debug("加载聊天上下文...")
            history_messages = self._load_chat_context(user_id, session_id)
            logger.debug("加载了 %d 条历史消息", len(history_messages))
            
            logger.debug("构建聊天提示词...")
            system_prompt, user_prompt = self._build_chat_prompts(query, ranked_results)
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
        deep_think: bool = True,
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

        stream = []
        history_messages = self._load_chat_context(user_id, session_id)
        logger.info("上下文=%s", history_messages)
        system_prompt, user_prompt = self._build_chat_prompts(query, ranked_results)
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
            result = self.kb.list_chunks(
                page_index=page_index,
                page_size=page_size,
                filename=filename,
                query=query,
            )
            if result is None:
                result = {}
            resp = {"ok": True, "count": int(result.get("total", 0)), "chunks": result.get("items", [])}
            return resp
        except Exception as exc:
            raise

    def update_chunk(self, chunk_id: int, text: str) -> Dict[str, Any]:
        try:
            self.kb.update_chunk(chunk_id=chunk_id, text=text)
            resp = {"ok": True}
            return resp
        except Exception as exc:
            raise

    def delete_chunk(self, chunk_id: int) -> Dict[str, Any]:
        try:
            self.kb.delete_chunk(chunk_id=chunk_id)
            resp = {"ok": True}
            return resp
        except Exception as exc:
            raise

    def rebuild_chunks_for_filename(self, filename: str) -> Dict[str, Any]:
        try:
            chunks = self.kb.rebuild_chunks_for_filename(filename)
            resp = {"ok": True, "chunks_added": int(chunks)}
            return resp
        except Exception as exc:
            raise

    def remove_document(self, filename: str) -> Dict[str, Any]:
        try:
            removed = self.kb.remove_document(filename)
            resp = {"ok": True, "chunks_removed": int(removed)}
            return resp
        except Exception as exc:
            raise

    def list_documents(self) -> Dict[str, Any]:
        docs = self.kb.list_documents()
        resp = {"ok": True, "count": len(docs), "documents": docs}
        return resp

    def get_knowledge_base_stats(self) -> Dict[str, Any]:
        stats = self.kb.stats()
        resp = {"ok": True, "stats": stats}
        return resp

    def clear_knowledge_base(self) -> Dict[str, Any]:
        try:
            self.kb.clear()
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

            def _send_json(self, status: int, payload: Any, page_index: int = 1) -> None:
                wrapped = self._wrap_payload(status=status, payload=payload, page_index=page_index)
                body = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_sse_headers(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

            def _send_sse(self, event: str, payload: Dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=False)
                message = f"event: {event}\ndata: {data}\n\n".encode("utf-8")
                self.wfile.write(message)
                self.wfile.flush()

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
                    path = self._path()
                    if path in {"/", "/ui", "/ui/"}:
                        if self._serve_static(WEB_DIR, "index.html"):
                            return
                        self._internal_error(FileNotFoundError("未找到前端入口文件: web/index.html"))
                        return
                    if path.startswith("/ui/"):
                        rel = path[len("/ui/") :]
                        if self._serve_static(WEB_DIR, rel):
                            return
                        self._not_found()
                        return
                    if path.startswith("/assets/"):
                        rel = path[len("/assets/") :]
                        if self._serve_static(ASSETS_DIR, rel):
                            return
                        self._not_found()
                        return
                    if path in {"/api-docs", "/docs", "/docs/"}:
                        if self._serve_static(DOCS_DIR, "API.html"):
                            return
                        self._internal_error(FileNotFoundError("未找到 API 文档文件: docs/API.html"))
                        return
                    if path.startswith("/docs/"):
                        rel = path[len("/docs/") :]
                        if self._serve_static(DOCS_DIR, rel):
                            return
                        self._not_found()
                        return
                    if path == "/health":
                        self._ok({"ok": True, "message": "服务正常"})
                        return
                    if path == "/session":
                        params = self._parse_query_params()
                        page_index = self._page_index_from_params(params)
                        user_id = None
                        if "user_id" in params and params["user_id"]:
                            user_id = params["user_id"][-1].strip() or None
                        if "userId" in params and params["userId"]:
                            user_id = params["userId"][-1].strip() or user_id
                        if not user_id:
                            self._bad_request("缺少 user_id 参数")
                            return
                        session_id = api._new_session_id(user_id)
                        self._ok(
                            {"ok": True, "user_id": user_id, "session_id": session_id},
                            page_index=page_index,
                        )
                        return
                    if path == "/query":
                        params = self._parse_query_params()
                        page_index = self._page_index_from_params(params)
                        stream_mode = False
                        if "stream" in params and params["stream"]:
                            stream_raw = params["stream"][-1].strip().lower()
                            stream_mode = stream_raw in {"1", "true", "yes", "on"}
                        user_id = None
                        session_id = None
                        if "user_id" in params and params["user_id"]:
                            user_id = params["user_id"][-1].strip() or None
                        if "userId" in params and params["userId"]:
                            user_id = params["userId"][-1].strip() or user_id
                        if "session_id" in params and params["session_id"]:
                            session_id = params["session_id"][-1].strip() or None
                        if "sessionId" in params and params["sessionId"]:
                            session_id = params["sessionId"][-1].strip() or session_id
                        if user_id and not session_id:
                            session_id = api._new_session_id(user_id)
                        query = ""
                        if "query" in params and params["query"]:
                            query = params["query"][-1].strip()
                        logger.info(
                            "HTTP /query GET: stream=%s query_len=%d user_id=%s session_id=%s",
                            stream_mode,
                            len(query),
                            bool(user_id),
                            bool(session_id),
                        )
                        if not query:
                            self._bad_request("缺少 query 参数")
                            return
                        try:
                            k = int(params.get("k", ["2"])[-1])
                        except Exception:
                            self._bad_request("k 必须是整数")
                            return
                        relevance_threshold = None
                        if "relevance_threshold" in params and params["relevance_threshold"]:
                            try:
                                relevance_threshold = float(params["relevance_threshold"][-1])
                            except Exception:
                                self._bad_request("relevance_threshold 必须是数字")
                                return
                        llm_model = None
                        if "llm_model" in params and params["llm_model"]:
                            llm_model = params["llm_model"][-1].strip() or None

                        model_config_id = None
                        if "model_config_id" in params and params["model_config_id"]:
                            try:
                                model_config_id = int(params["model_config_id"][-1])
                            except Exception:
                                self._bad_request("model_config_id 必须是整数")
                                return
                        model_config_name = None
                        if "model_config_name" in params and params["model_config_name"]:
                            model_config_name = params["model_config_name"][-1].strip() or None
                        use_default_model_config = False
                        if "use_default_model_config" in params and params["use_default_model_config"]:
                            raw = params["use_default_model_config"][-1].strip().lower()
                            if raw in {"1", "true", "yes", "on"}:
                                use_default_model_config = True
                            elif raw in {"0", "false", "no", "off"}:
                                use_default_model_config = False
                            else:
                                self._bad_request("use_default_model_config 必须是布尔值")
                                return

                        generate_answer = True
                        if "generate_answer" in params and params["generate_answer"]:
                            raw = params["generate_answer"][-1].strip().lower()
                            if raw in {"1", "true", "yes", "on"}:
                                generate_answer = True
                            elif raw in {"0", "false", "no", "off"}:
                                generate_answer = False
                            else:
                                self._bad_request("generate_answer 必须是布尔值")
                                return

                        deep_think = True
                        if "deep_think" in params and params["deep_think"]:
                            raw = params["deep_think"][-1].strip().lower()
                            if raw in {"1", "true", "yes", "on"}:
                                deep_think = True
                            elif raw in {"0", "false", "no", "off"}:
                                deep_think = False
                            else:
                                self._bad_request("deep_think 必须是布尔值")
                                return

                        temperature = 0.2
                        if "temperature" in params and params["temperature"]:
                            try:
                                temperature = float(params["temperature"][-1])
                            except Exception:
                                self._bad_request("temperature 必须是数字")
                                return

                        max_tokens = api._default_chat_max_tokens()
                        if "max_tokens" in params and params["max_tokens"]:
                            try:
                                max_tokens = int(params["max_tokens"][-1])
                            except Exception:
                                self._bad_request("max_tokens 必须是整数")
                                return

                        if stream_mode:
                            self._send_sse_headers()
                            data = api.query_stream(
                                query=query,
                                k=k,
                                relevance_threshold=relevance_threshold,
                                llm_model=llm_model,
                                model_config_id=model_config_id,
                                model_config_name=model_config_name,
                                use_default_model_config=use_default_model_config,
                                generate_answer=generate_answer,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                user_id=user_id,
                                session_id=session_id,
                                deep_think=deep_think,
                            )
                            answer_parts: List[str] = []
                            self._send_sse(
                                "meta",
                                {
                                    "results": data.get("results", []),
                                    "session_id": session_id,
                                    "user_id": user_id,
                                },
                            )
                            finish_reason = "stop"
                            answer_text = ""
                            thinking_text = ""
                            thinking_summary = data.get("thinking_summary")
                            if generate_answer:
                                split_state = api._init_stream_split_state()
                                answer_parts: List[str] = []
                                thinking_parts: List[str] = []
                                for piece in data.get("stream", []):
                                    text = str(piece or "")
                                    if not text:
                                        continue
                                    routed = api._feed_stream_split_state(split_state, text)
                                    for channel, delta_piece in routed:
                                        if not delta_piece:
                                            continue
                                        if channel == "thinking":
                                            thinking_parts.append(delta_piece)
                                            self._send_sse("thinking_delta", {"delta": delta_piece})
                                        else:
                                            answer_parts.append(delta_piece)
                                            self._send_sse("delta", {"delta": delta_piece})
                                final_answer, final_thinking, parsed_summary = api._finalize_stream_split_state(split_state)
                                sent_answer = "".join(answer_parts)
                                sent_thinking = "".join(thinking_parts)
                                if final_thinking and len(final_thinking) > len(sent_thinking):
                                    tail = final_thinking[len(sent_thinking):]
                                    if tail:
                                        thinking_parts.append(tail)
                                        self._send_sse("thinking_delta", {"delta": tail})
                                if final_answer and len(final_answer) > len(sent_answer):
                                    tail = final_answer[len(sent_answer):]
                                    if tail:
                                        answer_parts.append(tail)
                                        self._send_sse("delta", {"delta": tail})
                                answer_text = "".join(answer_parts)
                                thinking_text = "".join(thinking_parts).strip()
                                if parsed_summary and not thinking_summary:
                                    thinking_summary = parsed_summary
                            else:
                                answer_parts: List[str] = []
                                finish_reason = "not_requested"
                                thinking_summary = None
                            logger.info(
                                "SSE stream completed: chunks=%d chars=%d finish_reason=%s",
                                len(answer_parts),
                                len(answer_text),
                                finish_reason,
                            )
                            resp = {
                                "answer": answer_text,
                                "finish_reason": finish_reason,
                                "is_complete": True,
                                "results": data.get("results", []),
                                "session_id": session_id,
                                "user_id": user_id,
                                "thinking": thinking_text,
                                "thinking_summary": thinking_summary,
                                "messages": [
                                    {"role": "system", "content": data.get("system_prompt", "")},
                                    *data.get("history_messages", []),
                                    {"role": "user", "content": data.get("user_prompt", query)},
                                    {"role": "assistant", "content": answer_text},
                                ],
                            }
                            api._append_history("query", data.get("req", {}), resp, thinking_summary=thinking_summary)
                            self._send_sse(
                                "done",
                                {
                                    "answer": answer_text,
                                    "finish_reason": finish_reason,
                                    "thinking": thinking_text,
                                    "thinking_summary": thinking_summary,
                                },
                            )
                            return
                        self._ok(
                            api.query(
                                query=query,
                                k=k,
                                relevance_threshold=relevance_threshold,
                                llm_model=llm_model,
                                model_config_id=model_config_id,
                                model_config_name=model_config_name,
                                use_default_model_config=use_default_model_config,
                                generate_answer=generate_answer,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                user_id=user_id,
                                session_id=session_id,
                                deep_think=deep_think,
                            ),
                            page_index=page_index,
                        )
                        return
                    if path == "/stats":
                        self._ok(api.get_knowledge_base_stats())
                        return
                    if path == "/kb/documents":
                        self._ok(api.list_documents())
                        return
                    if path == "/kb/chunks":
                        params = self._parse_query_params()
                        page_index = self._page_index_from_params(params)
                        page_size = 20
                        filename = None
                        query = None
                        
                        page_size_str = self._get_param_value(params, "pageSize", "")
                        if page_size_str:
                            try:
                                page_size = int(page_size_str)
                            except Exception:
                                self._bad_request("pageSize 必须是整数")
                                return
                        
                        filename = self._get_param_value(params, "filename", "").strip() or None
                        query = self._get_param_value(params, "q", "").strip() or None
                        self._ok(
                            api.list_chunks(
                                page_index=page_index,
                                page_size=page_size,
                                filename=filename,
                                query=query,
                            ),
                            page_index=page_index,
                        )
                        return
                    if path == "/history":
                        params = self._parse_query_params()
                        page_index = self._page_index_from_params(params)
                        limit = None
                        action = None
                        group_by_session = False
                        
                        if "limit" in params and params["limit"]:
                            try:
                                limit = int(params["limit"][-1])
                            except Exception:
                                self._bad_request("limit 必须是整数")
                                return
                        if "action" in params and params["action"]:
                            action = params["action"][-1]
                        if "group_by_session" in params and params["group_by_session"]:
                            group_by_session = params["group_by_session"][-1].lower() in ("true", "1", "yes")
                        
                        if group_by_session:
                            result = {"ok": True, "sessions": api.get_history_sessions(limit=limit, action=action)}
                        else:
                            result = {"ok": True, "history": api.get_history(limit=limit, action=action)}
                        
                        self._ok(result, page_index=page_index)
                        return
                    
                    # Model configuration endpoints
                    if path == "/model/configs":
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        params = self._parse_query_params()
                        provider = self._get_param_value(params, "provider", "").strip() or None
                        is_active_str = self._get_param_value(params, "is_active", "").strip()
                        is_active = None
                        if is_active_str:
                            is_active = is_active_str.lower() in ("true", "1", "yes")
                        model_type = self._get_param_value(params, "model_type", "").strip() or None
                        result = api._model_config_manager.list_model_configs(
                            provider=provider,
                            is_active=is_active,
                            model_type=model_type,
                        )
                        self._ok(result)
                        return
                    
                    if path.startswith("/model/config/"):
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        # Extract ID or name
                        identifier = unquote(path[len("/model/config/"):]).strip()
                        if not identifier:
                            self._bad_request("缺少 config_id 或 name 参数")
                            return
                        # Try to parse as ID first
                        try:
                            config_id = int(identifier)
                            result = api._model_config_manager.get_model_config(config_id=config_id)
                        except ValueError:
                            # Use as name
                            result = api._model_config_manager.get_model_config(name=identifier)
                        self._ok(result)
                        return
                    
                    if path == "/model/config/default":
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        result = api._model_config_manager.get_default_config()
                        self._ok(result)
                        return
                    
                    if path == "/model/providers":
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        result = api._model_config_manager.get_supported_providers()
                        self._ok(result)
                        return
                    
                    self._not_found()
                except Exception as exc:
                    self._internal_error(exc)

            def do_POST(self):  # noqa: N802
                try:
                    path = self._path()
                    if path == "/kb/file":
                        content_type = self.headers.get("Content-Type", "")
                        if "multipart/form-data" in content_type.lower():
                            uploaded = self._read_multipart_file("file")
                            form = uploaded.get("form", {})
                            page_index = self._to_positive_int(form.get("pageIndex", 1), default=1)
                            filename = str(form.get("filename") or uploaded.get("filename") or "").strip()
                            if not filename:
                                self._bad_request("缺少 filename 参数")
                                return
                            encoding = str(form.get("encoding", "")).strip() or None
                            self._ok(
                                api.add_uploaded_file(
                                    filename=filename,
                                    content=uploaded["content"],
                                    encoding=encoding,
                                ),
                                page_index=page_index,
                            )
                            return
                        body = self._read_json()
                        page_index = self._page_index_from_body(body)
                        filename = str(body.get("filename", "")).strip()
                        text = body.get("text")
                        if not filename or text is None:
                            self._bad_request(
                                "请使用 multipart/form-data 并携带 file 字段，或使用 JSON 并提供 filename/text"
                            )
                            return
                        self._ok(api.add_document(filename=filename, text=str(text)), page_index=page_index)
                        return
                    if path == "/kb/files":
                        content_type = self.headers.get("Content-Type", "")
                        if "multipart/form-data" not in content_type.lower():
                            self._bad_request("请使用 multipart/form-data 并携带 files 字段")
                            return
                        uploaded = self._read_multipart_files("files")
                        form = uploaded.get("form", {})
                        page_index = self._to_positive_int(form.get("pageIndex", 1), default=1)
                        encoding = str(form.get("encoding", "")).strip() or None
                        files = uploaded.get("files", [])
                        for item in files:
                            if not str(item.get("filename") or "").strip():
                                self._bad_request("缺少 filename 参数")
                                return
                        self._ok(
                            api.add_uploaded_files(files=files, encoding=encoding),
                            page_index=page_index,
                        )
                        return
                    body = self._read_json()
                    page_index = self._page_index_from_body(body)
                    if path == "/session":
                        user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None
                        if not user_id:
                            self._bad_request("缺少 user_id 参数")
                            return
                        session_id = api._new_session_id(user_id)
                        self._ok(
                            {"ok": True, "user_id": user_id, "session_id": session_id},
                            page_index=page_index,
                        )
                        return
                    if path == "/query":
                        query = str(body.get("query", "")).strip()
                        if not query:
                            self._bad_request("缺少 query 参数")
                            return
                        user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None
                        session_id = str(body.get("session_id") or body.get("sessionId") or "").strip() or None
                        if user_id and not session_id:
                            session_id = api._new_session_id(user_id)
                        generate_answer_raw = body.get("generate_answer", True)
                        if isinstance(generate_answer_raw, bool):
                            generate_answer = generate_answer_raw
                        elif isinstance(generate_answer_raw, (int, float)):
                            generate_answer = bool(generate_answer_raw)
                        elif isinstance(generate_answer_raw, str):
                            val = generate_answer_raw.strip().lower()
                            if val in {"1", "true", "yes", "on"}:
                                generate_answer = True
                            elif val in {"0", "false", "no", "off"}:
                                generate_answer = False
                            else:
                                self._bad_request("generate_answer 必须是布尔值")
                                return
                        else:
                            self._bad_request("generate_answer 必须是布尔值")
                            return
                        deep_think_raw = body.get("deep_think", True)
                        if isinstance(deep_think_raw, bool):
                            deep_think = deep_think_raw
                        elif isinstance(deep_think_raw, (int, float)):
                            deep_think = bool(deep_think_raw)
                        elif isinstance(deep_think_raw, str):
                            val = deep_think_raw.strip().lower()
                            if val in {"1", "true", "yes", "on"}:
                                deep_think = True
                            elif val in {"0", "false", "no", "off"}:
                                deep_think = False
                            else:
                                self._bad_request("deep_think 必须是布尔值")
                                return
                        else:
                            deep_think = True
                        k = int(body.get("k", 2))
                        threshold_raw = body.get("relevance_threshold")
                        relevance_threshold = (
                            None if threshold_raw is None else float(threshold_raw)
                        )
                        llm_model = str(body.get("llm_model", "")).strip() or None
                        model_config_id = body.get("model_config_id")
                        if model_config_id is not None:
                            model_config_id = int(model_config_id)
                        model_config_name = str(body.get("model_config_name", "")).strip() or None
                        use_default_model_config = bool(body.get("use_default_model_config", False))
                        temperature_raw = body.get("temperature", 0.2)
                        max_tokens_raw = body.get("max_tokens")
                        temperature = None if temperature_raw is None else float(temperature_raw)
                        if max_tokens_raw is None:
                            max_tokens = api._default_chat_max_tokens()
                        else:
                            max_tokens = int(max_tokens_raw)
                        stream_mode = bool(body.get("stream", False))
                        logger.info(
                            "HTTP /query POST: stream=%s query_len=%d user_id=%s session_id=%s generate_answer=%s deep_think=%s",
                            stream_mode,
                            len(query),
                            bool(user_id),
                            bool(session_id),
                            generate_answer,
                            deep_think,
                        )
                        if stream_mode:
                            self._send_sse_headers()
                            data = api.query_stream(
                                query=query,
                                k=k,
                                relevance_threshold=relevance_threshold,
                                llm_model=llm_model,
                                model_config_id=model_config_id,
                                model_config_name=model_config_name,
                                use_default_model_config=use_default_model_config,
                                generate_answer=generate_answer,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                user_id=user_id,
                                session_id=session_id,
                                deep_think=deep_think,
                            )
                            answer_parts: List[str] = []
                            self._send_sse(
                                "meta",
                                {
                                    "results": data.get("results", []),
                                    "session_id": session_id,
                                    "user_id": user_id,
                                },
                            )
                            finish_reason = "stop"
                            answer_text = ""
                            thinking_text = ""
                            thinking_summary = data.get("thinking_summary")
                            if generate_answer:
                                split_state = api._init_stream_split_state()
                                answer_parts: List[str] = []
                                thinking_parts: List[str] = []
                                for piece in data.get("stream", []):
                                    text = str(piece or "")
                                    if not text:
                                        continue
                                    routed = api._feed_stream_split_state(split_state, text)
                                    for channel, delta_piece in routed:
                                        if not delta_piece:
                                            continue
                                        if channel == "thinking":
                                            thinking_parts.append(delta_piece)
                                            self._send_sse("thinking_delta", {"delta": delta_piece})
                                        else:
                                            answer_parts.append(delta_piece)
                                            self._send_sse("delta", {"delta": delta_piece})
                                final_answer, final_thinking, parsed_summary = api._finalize_stream_split_state(split_state)
                                sent_answer = "".join(answer_parts)
                                sent_thinking = "".join(thinking_parts)
                                if final_thinking and len(final_thinking) > len(sent_thinking):
                                    tail = final_thinking[len(sent_thinking):]
                                    if tail:
                                        thinking_parts.append(tail)
                                        self._send_sse("thinking_delta", {"delta": tail})
                                if final_answer and len(final_answer) > len(sent_answer):
                                    tail = final_answer[len(sent_answer):]
                                    if tail:
                                        answer_parts.append(tail)
                                        self._send_sse("delta", {"delta": tail})
                                answer_text = "".join(answer_parts)
                                thinking_text = "".join(thinking_parts).strip()
                                if parsed_summary and not thinking_summary:
                                    thinking_summary = parsed_summary
                            else:
                                answer_parts: List[str] = []
                                finish_reason = "not_requested"
                                thinking_summary = None
                            logger.info(
                                "SSE stream completed: chunks=%d chars=%d finish_reason=%s",
                                len(answer_parts),
                                len(answer_text),
                                finish_reason,
                            )
                            resp = {
                                "answer": answer_text,
                                "finish_reason": finish_reason,
                                "is_complete": True,
                                "results": data.get("results", []),
                                "session_id": session_id,
                                "user_id": user_id,
                                "thinking": thinking_text,
                                "thinking_summary": thinking_summary,
                                "messages": [
                                    {"role": "system", "content": data.get("system_prompt", "")},
                                    *data.get("history_messages", []),
                                    {"role": "user", "content": data.get("user_prompt", query)},
                                    {"role": "assistant", "content": answer_text},
                                ],
                            }
                            api._append_history("query", data.get("req", {}), resp, thinking_summary=thinking_summary)
                            self._send_sse(
                                "done",
                                {
                                    "answer": answer_text,
                                    "finish_reason": finish_reason,
                                    "thinking": thinking_text,
                                    "thinking_summary": thinking_summary,
                                },
                            )
                            return
                        self._ok(
                            api.query(
                                query=query,
                                k=k,
                                relevance_threshold=relevance_threshold,
                                llm_model=llm_model,
                                model_config_id=model_config_id,
                                model_config_name=model_config_name,
                                use_default_model_config=use_default_model_config,
                                generate_answer=generate_answer,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                user_id=user_id,
                                session_id=session_id,
                                deep_think=deep_think,
                            ),
                            page_index=page_index,
                        )
                        return
                    if path == "/kb/document":
                        filename = str(body.get("filename", "")).strip()
                        text = str(body.get("text", ""))
                        if not filename:
                            self._bad_request("缺少 filename 参数")
                            return
                        self._ok(api.add_document(filename=filename, text=text), page_index=page_index)
                        return
                    if path == "/kb/chunks/rebuild":
                        filename = str(body.get("filename", "")).strip()
                        if not filename:
                            self._bad_request("缺少 filename 参数")
                            return
                        self._ok(api.rebuild_chunks_for_filename(filename), page_index=page_index)
                        return
                    
                    # Model configuration POST endpoints
                    if path == "/model/config":
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        # Add new config
                        required_fields = ["name", "provider", "base_url", "model_name"]
                        for field in required_fields:
                            if not body.get(field):
                                self._bad_request(f"缺少必填字段: {field}")
                                return
                        result = api._model_config_manager.add_model_config(
                            name=body["name"],
                            provider=body["provider"],
                            base_url=body["base_url"],
                            model_name=body["model_name"],
                            api_key=body.get("api_key"),
                            model_type=body.get("model_type", "chat"),
                            temperature=body.get("temperature", 0.7),
                            max_tokens=body.get("max_tokens"),
                            timeout=body.get("timeout", 30.0),
                            extra_headers=body.get("extra_headers"),
                            extra_params=body.get("extra_params"),
                            is_active=body.get("is_active", True),
                            is_default=body.get("is_default", False),
                            description=body.get("description"),
                        )
                        self._ok(result, page_index=page_index)
                        return
                    
                    if path == "/model/config/test":
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        # Test config
                        config_id = body.get("config_id")
                        name = body.get("name")
                        config_data = body.get("config")
                        result = api._model_config_manager.test_config(
                            config_id=config_id,
                            name=name,
                            config_data=config_data,
                        )
                        self._ok(result, page_index=page_index)
                        return

                    if path == "/model/config/bootstrap":
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        result = api._model_config_manager.bootstrap_default_configs()
                        self._ok(result, page_index=page_index)
                        return
                    
                    if path.startswith("/model/config/") and path.endswith("/default"):
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        # Set as default
                        config_id_str = path[len("/model/config/"):-len("/default")]
                        try:
                            config_id = int(config_id_str)
                        except ValueError:
                            self._bad_request("config_id 必须是整数")
                            return
                        result = api._model_config_manager.set_default_config(config_id)
                        self._ok(result, page_index=page_index)
                        return
                    
                    self._not_found()
                except ValueError as exc:
                    self._bad_request(str(exc))
                except Exception as exc:
                    self._internal_error(exc)

            def do_PUT(self):  # noqa: N802
                try:
                    path = self._path()
                    if path.startswith("/kb/chunk/"):
                        chunk_id_raw = unquote(path[len("/kb/chunk/") :]).strip()
                        if not chunk_id_raw:
                            self._bad_request("缺少 chunk_id 参数")
                            return
                        try:
                            chunk_id = int(chunk_id_raw)
                        except Exception:
                            self._bad_request("chunk_id 必须是整数")
                            return
                        body = self._read_json()
                        page_index = self._page_index_from_body(body)
                        text = str(body.get("text", ""))
                        if not text.strip():
                            self._bad_request("缺少 text 参数")
                            return
                        self._ok(api.update_chunk(chunk_id=chunk_id, text=text), page_index=page_index)
                        return
                    
                    # Model configuration PUT endpoint
                    if path.startswith("/model/config/"):
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        config_id_str = unquote(path[len("/model/config/"):]).strip()
                        try:
                            config_id = int(config_id_str)
                        except ValueError:
                            self._bad_request("config_id 必须是整数")
                            return
                        body = self._read_json()
                        page_index = self._page_index_from_body(body)
                        # Update config with provided fields
                        update_fields = {}
                        allowed_fields = [
                            "name", "provider", "base_url", "api_key", "model_name", "model_type",
                            "temperature", "max_tokens", "timeout", "extra_headers", "extra_params",
                            "is_active", "is_default", "description"
                        ]
                        for field in allowed_fields:
                            if field in body:
                                update_fields[field] = body[field]
                        result = api._model_config_manager.update_model_config(config_id, **update_fields)
                        self._ok(result, page_index=page_index)
                        return
                    
                    self._not_found()
                except ValueError as exc:
                    self._bad_request(str(exc))
                except Exception as exc:
                    self._internal_error(exc)

            def do_DELETE(self):  # noqa: N802
                try:
                    path = self._path()
                    if path == "/kb":
                        self._ok(api.clear_knowledge_base())
                        return
                    if path == "/history":
                        removed = api.clear_history()
                        self._ok({"ok": True, "removed": removed})
                        return
                    if path.startswith("/history/"):
                        raw_id = unquote(path[len("/history/") :]).strip()
                        if not raw_id:
                            self._bad_request("缺少 history id 参数")
                            return
                        try:
                            item_id = int(raw_id)
                        except Exception:
                            self._bad_request("history id 必须是整数")
                            return
                        removed = api.delete_history(item_id)
                        if removed <= 0:
                            self._not_found()
                            return
                        self._ok({"ok": True, "removed": removed})
                        return
                    if path.startswith("/session/"):
                        session_id = unquote(path[len("/session/") :]).strip()
                        if not session_id:
                            self._bad_request("缺少 session_id 参数")
                            return
                        try:
                            removed = api.delete_session(session_id)
                            if removed <= 0:
                                self._not_found()
                                return
                            self._ok({"ok": True, "removed": removed})
                        except NotImplementedError:
                            self._bad_request("当前后端不支持删除整段会话")
                        return
                    if path.startswith("/kb/document/"):
                        filename = unquote(path[len("/kb/document/") :]).strip()
                        if not filename:
                            self._bad_request("缺少 filename 参数")
                            return
                        self._ok(api.remove_document(filename))
                        return
                    if path.startswith("/kb/chunk/"):
                        chunk_id_raw = unquote(path[len("/kb/chunk/") :]).strip()
                        if not chunk_id_raw:
                            self._bad_request("缺少 chunk_id 参数")
                            return
                        try:
                            chunk_id = int(chunk_id_raw)
                        except Exception:
                            self._bad_request("chunk_id 必须是整数")
                            return
                        self._ok(api.delete_chunk(chunk_id))
                        return
                    
                    # Model configuration DELETE endpoint
                    if path.startswith("/model/config/"):
                        if not api._model_config_manager:
                            self._bad_request("模型配置管理不可用（需要启用数据库后端）")
                            return
                        config_id_str = unquote(path[len("/model/config/"):]).strip()
                        try:
                            config_id = int(config_id_str)
                        except ValueError:
                            self._bad_request("config_id 必须是整数")
                            return
                        result = api._model_config_manager.delete_model_config(config_id)
                        if not result.get("ok"):
                            self._not_found()
                            return
                        self._ok(result)
                        return
                    
                    self._not_found()
                except Exception as exc:
                    self._internal_error(exc)

        return Handler

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
