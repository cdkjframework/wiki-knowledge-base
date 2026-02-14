from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import parse_qs, unquote, urlparse

try:
    from .history_store import DatabaseHistoryStore, InMemoryHistoryStore
except ImportError:  # pragma: no cover
    from history_store import DatabaseHistoryStore, InMemoryHistoryStore

try:
    from .knowledge_base import KnowledgeBase
except ImportError:  # pragma: no cover
    from knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class KnowledgeBaseApi:

    def __init__(self, knowledge_base: KnowledgeBase):
        self.kb = knowledge_base
        self._history_store = self._init_history_store()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_history(
        self,
        action: str,
        request: Dict[str, Any],
        response: Dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Dict[str, Any]:
        return self._history_store.append(
            timestamp=self._now_iso(),
            action=action,
            request=request,
            response=response,
            error=error,
        )

    @staticmethod
    def _load_project_config() -> Dict[str, Any]:
        cfg_path = Path(__file__).resolve().parent.parent / "config.json"
        if not cfg_path.exists():
            return {}
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _init_history_store(self):
        config = self._load_project_config()
        history_cfg = config.get("history", {})
        if not isinstance(history_cfg, dict):
            history_cfg = {}

        backend_raw = os.getenv("KB_HISTORY_BACKEND") or history_cfg.get("backend") or "memory"
        backend = str(backend_raw or "").strip().lower()
        if backend in {"", "memory", "in_memory", "none"}:
            logger.info("History storage backend: memory")
            return InMemoryHistoryStore()
        if backend == "postgres":
            backend = "postgresql"
        if backend not in {"mysql", "postgresql"}:
            raise ValueError(f"Unsupported history backend: {backend}")

        db_cfg_key = "mysql" if backend == "mysql" else "postgresql"
        db_cfg = history_cfg.get(db_cfg_key, {})
        if not isinstance(db_cfg, dict):
            db_cfg = {}

        default_port = 3306 if backend == "mysql" else 5432
        env_prefix = "KB_HISTORY_MYSQL_" if backend == "mysql" else "KB_HISTORY_PG_"

        host = os.getenv(env_prefix + "HOST") or db_cfg.get("host", "127.0.0.1")
        port = os.getenv(env_prefix + "PORT") or db_cfg.get("port", default_port)
        user = os.getenv(env_prefix + "USER") or db_cfg.get("user", "")
        password = os.getenv(env_prefix + "PASSWORD") or db_cfg.get("password", "")
        database = os.getenv(env_prefix + "DATABASE") or db_cfg.get("database", "knowledge_base")
        table = os.getenv("KB_HISTORY_TABLE") or history_cfg.get("table", "kb_history")
        timeout = os.getenv(env_prefix + "CONNECT_TIMEOUT") or db_cfg.get("connect_timeout", 5)

        store = DatabaseHistoryStore(
            backend=backend,
            host=str(host),
            port=int(port),
            user=str(user),
            password=str(password),
            database=str(database),
            table=str(table),
            connect_timeout=int(timeout),
        )
        logger.info(
            "History storage backend: %s (%s:%s/%s table=%s)",
            backend,
            host,
            port,
            database,
            table,
        )
        return store

    def log_event(self, action: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self._append_history(
            action=action,
            request=payload or {},
            response={"ok": True},
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
            "No chat model configured. Set KB_CHAT_MODEL or knowledge_base.lm_studio.chat_model."
        )

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

    def _answer_from_lm_studio(
        self,
        question: str,
        results: Sequence[Dict[str, Any]],
        llm_model: str | None = None,
        temperature: float | None = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        model = self._resolve_llm_model(llm_model)
        context = self._build_context(results)
        if not context:
            return "No relevant knowledge-base content was retrieved."

        system_prompt = (
            "You are a knowledge-base assistant. Answer only from the provided context. "
            "If evidence is insufficient, say that the answer is unknown from current knowledge."
        )
        user_prompt = (
            f"Question: {question}\n\n"
            f"Knowledge context:\n{context}\n\n"
            "Provide a concise and accurate answer."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        answer = self.kb.chat_once(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return str(answer or "").strip()

    @staticmethod
    def _distance_to_similarity(distance: float) -> float:
        dist = float(distance)
        if dist < 0:
            dist = 0.0
        return 1.0 / (1.0 + dist)

    def query(
        self,
        query: str,
        k: int = 2,
        relevance_threshold: float | None = None,
        llm_model: str | None = None,
        generate_answer: bool = True,
        temperature: float | None = 0.2,
        max_tokens: int | None = None,
    ) -> Dict[str, Any]:
        logger.info("API query called: k=%s generate_answer=%s", k, generate_answer)
        req = {
            "query": query,
            "k": int(k),
            "relevance_threshold": (
                None if relevance_threshold is None else float(relevance_threshold)
            ),
            "llm_model": llm_model,
            "generate_answer": bool(generate_answer),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            raw = self.kb.search(query=query, k=k, relevance_threshold=relevance_threshold)
            ranked_results = []
            result_items = []
            for fn, text, distance_raw in raw:
                distance = max(0.0, float(distance_raw))
                similarity = self._distance_to_similarity(distance)
                ranked_results.append({"filename": fn, "text": text, "score": similarity})
                result_items.append(
                    {
                        "distance": round(float(distance), 4),
                        "filename": str(fn),
                        "similarity": round(float(similarity), 4),
                    }
                )
            answer = ""
            finish_reason = "stop"
            is_complete = True
            if generate_answer:
                answer = self._answer_from_lm_studio(
                    question=query,
                    results=ranked_results,
                    llm_model=llm_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            else:
                finish_reason = "not_requested"
            resp: Dict[str, Any] = {
                "answer": answer,
                "finish_reason": finish_reason,
                "is_complete": bool(is_complete),
                "results": result_items,
            }
            self._append_history("query", req, resp)
            logger.info("API query completed: results=%s", len(result_items))
            return resp
        except Exception as exc:
            self._append_history("query", req, {"ok": False}, error=str(exc))
            logger.exception("API query failed")
            raise

    def add_document(self, filename: str, text: str) -> Dict[str, Any]:
        req = {"filename": filename, "text_length": len((text or "").strip())}
        try:
            chunks = self.kb.add_document(filename, text)
            resp = {"ok": True, "chunks_added": int(chunks)}
            self._append_history("add_document", req, resp)
            return resp
        except Exception as exc:
            self._append_history("add_document", req, {"ok": False}, error=str(exc))
            raise

    def add_file(self, file_path: str) -> Dict[str, Any]:
        req = {"file_path": file_path}
        try:
            chunks = self.kb.add_text_file(file_path)
            resp = {"ok": True, "chunks_added": int(chunks)}
            self._append_history("add_file", req, resp)
            return resp
        except Exception as exc:
            self._append_history("add_file", req, {"ok": False}, error=str(exc))
            raise

    def add_uploaded_file(
        self, filename: str, content: bytes, encoding: str | None = None
    ) -> Dict[str, Any]:
        req = {
            "filename": filename,
            "content_length": len(content or b""),
            "encoding": encoding,
        }
        try:
            chunks = self.kb.add_uploaded_file(filename=filename, content=content, encoding=encoding)
            resp = {"ok": True, "chunks_added": int(chunks)}
            self._append_history("add_uploaded_file", req, resp)
            return resp
        except Exception as exc:
            self._append_history("add_uploaded_file", req, {"ok": False}, error=str(exc))
            raise

    def add_files(self, file_paths: Sequence[str]) -> Dict[str, Any]:
        req = {"file_paths": list(file_paths)}
        try:
            chunks = self.kb.add_files(file_paths)
            resp = {"ok": True, "chunks_added": int(chunks)}
            self._append_history("add_files", req, resp)
            return resp
        except Exception as exc:
            self._append_history("add_files", req, {"ok": False}, error=str(exc))
            raise

    def ingest_dir(self, root_dir: str, extensions: Sequence[str] | None = None) -> Dict[str, Any]:
        req = {
            "root_dir": root_dir,
            "extensions": list(extensions) if extensions is not None else None,
        }
        try:
            if extensions is None:
                chunks = self.kb.ingest_dir(root_dir)
            else:
                chunks = self.kb.ingest_dir(root_dir, extensions=extensions)
            resp = {"ok": True, "chunks_added": int(chunks)}
            self._append_history("ingest_dir", req, resp)
            return resp
        except Exception as exc:
            self._append_history("ingest_dir", req, {"ok": False}, error=str(exc))
            raise

    def remove_document(self, filename: str) -> Dict[str, Any]:
        req = {"filename": filename}
        try:
            removed = self.kb.remove_document(filename)
            resp = {"ok": True, "chunks_removed": int(removed)}
            self._append_history("remove_document", req, resp)
            return resp
        except Exception as exc:
            self._append_history("remove_document", req, {"ok": False}, error=str(exc))
            raise

    def list_documents(self) -> Dict[str, Any]:
        req: Dict[str, Any] = {}
        docs = self.kb.list_documents()
        resp = {"ok": True, "count": len(docs), "documents": docs}
        self._append_history("list_documents", req, resp)
        return resp

    def get_knowledge_base_stats(self) -> Dict[str, Any]:
        req: Dict[str, Any] = {}
        stats = self.kb.stats()
        resp = {"ok": True, "stats": stats}
        self._append_history("get_knowledge_base_stats", req, resp)
        return resp

    def clear_knowledge_base(self) -> Dict[str, Any]:
        req: Dict[str, Any] = {}
        try:
            self.kb.clear()
            resp = {"ok": True}
            self._append_history("clear_knowledge_base", req, resp)
            return resp
        except Exception as exc:
            self._append_history("clear_knowledge_base", req, {"ok": False}, error=str(exc))
            raise

    def get_history(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        return self._history_store.get(limit=limit, action=action)

    def clear_history(self) -> int:
        return self._history_store.clear()


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

            def _ok(self, payload: Any, page_index: int = 1) -> None:
                self._send_json(200, payload, page_index=page_index)

            def _bad_request(self, message: str, page_index: int = 1) -> None:
                self._send_json(400, {"error": message}, page_index=page_index)

            def _not_found(self, page_index: int = 1) -> None:
                self._send_json(404, {"error": "Not found"}, page_index=page_index)

            def _internal_error(self, exc: Exception, page_index: int = 1) -> None:
                self._send_json(500, {"error": str(exc)}, page_index=page_index)

            def _read_body_bytes(self) -> bytes:
                length_raw = self.headers.get("Content-Length", "").strip()
                if not length_raw:
                    return b""
                try:
                    length = int(length_raw)
                except Exception:
                    raise ValueError("Invalid Content-Length")
                return self.rfile.read(max(0, length))

            def _read_json(self) -> Dict[str, Any]:
                raw = self._read_body_bytes()
                if not raw:
                    return {}
                try:
                    obj = json.loads(raw.decode("utf-8"))
                except Exception as exc:
                    raise ValueError("Invalid JSON body") from exc
                if not isinstance(obj, dict):
                    raise ValueError("JSON body must be an object")
                return obj

            def _read_multipart_file(self, field_name: str = "file") -> Dict[str, Any]:
                content_type = self.headers.get("Content-Type", "")
                if "multipart/form-data" not in content_type.lower():
                    raise ValueError("Content-Type must be multipart/form-data")

                raw = self._read_body_bytes()
                if not raw:
                    raise ValueError("Request body is empty")

                header = (
                    f"Content-Type: {content_type}\r\n"
                    "MIME-Version: 1.0\r\n\r\n"
                ).encode("utf-8")
                message = BytesParser(policy=default).parsebytes(header + raw)
                if not message.is_multipart():
                    raise ValueError("Invalid multipart body")

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
                    raise ValueError(f"{field_name} is required")

                uploaded["form"] = form
                return uploaded

            def _parse_query_params(self) -> Dict[str, List[str]]:
                parsed = urlparse(self.path)
                return parse_qs(parsed.query, keep_blank_values=True)

            @staticmethod
            def _to_positive_int(value: Any, default: int = 1) -> int:
                try:
                    num = int(value)
                except Exception:
                    return int(default)
                return num if num > 0 else int(default)

            def _page_index_from_params(self, params: Dict[str, List[str]]) -> int:
                raw = params.get("pageIndex", ["1"])[-1] if isinstance(params, dict) else "1"
                return self._to_positive_int(raw, default=1)

            def _page_index_from_body(self, body: Dict[str, Any]) -> int:
                raw = body.get("pageIndex", 1) if isinstance(body, dict) else 1
                return self._to_positive_int(raw, default=1)

            def _path(self) -> str:
                return urlparse(self.path).path

            def log_message(self, fmt: str, *args):  # noqa: D401
                # Keep stdout clean for service mode.
                return

            def do_GET(self):  # noqa: N802
                try:
                    path = self._path()
                    if path == "/health":
                        self._ok({"ok": True, "message": "alive"})
                        return
                    if path == "/query":
                        params = self._parse_query_params()
                        page_index = self._page_index_from_params(params)
                        query = ""
                        if "query" in params and params["query"]:
                            query = params["query"][-1].strip()
                        if not query:
                            self._bad_request("query is required")
                            return
                        try:
                            k = int(params.get("k", ["2"])[-1])
                        except Exception:
                            self._bad_request("k must be int")
                            return
                        relevance_threshold = None
                        if "relevance_threshold" in params and params["relevance_threshold"]:
                            try:
                                relevance_threshold = float(params["relevance_threshold"][-1])
                            except Exception:
                                self._bad_request("relevance_threshold must be float")
                                return
                        llm_model = None
                        if "llm_model" in params and params["llm_model"]:
                            llm_model = params["llm_model"][-1].strip() or None

                        generate_answer = True
                        if "generate_answer" in params and params["generate_answer"]:
                            raw = params["generate_answer"][-1].strip().lower()
                            if raw in {"1", "true", "yes", "on"}:
                                generate_answer = True
                            elif raw in {"0", "false", "no", "off"}:
                                generate_answer = False
                            else:
                                self._bad_request("generate_answer must be bool")
                                return

                        temperature = 0.2
                        if "temperature" in params and params["temperature"]:
                            try:
                                temperature = float(params["temperature"][-1])
                            except Exception:
                                self._bad_request("temperature must be float")
                                return

                        max_tokens = None
                        if "max_tokens" in params and params["max_tokens"]:
                            try:
                                max_tokens = int(params["max_tokens"][-1])
                            except Exception:
                                self._bad_request("max_tokens must be int")
                                return

                        self._ok(
                            api.query(
                                query=query,
                                k=k,
                                relevance_threshold=relevance_threshold,
                                llm_model=llm_model,
                                generate_answer=generate_answer,
                                temperature=temperature,
                                max_tokens=max_tokens,
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
                    if path == "/history":
                        params = self._parse_query_params()
                        page_index = self._page_index_from_params(params)
                        limit = None
                        action = None
                        if "limit" in params and params["limit"]:
                            try:
                                limit = int(params["limit"][-1])
                            except Exception:
                                self._bad_request("limit must be int")
                                return
                        if "action" in params and params["action"]:
                            action = params["action"][-1]
                        self._ok(
                            {"ok": True, "history": api.get_history(limit=limit, action=action)},
                            page_index=page_index,
                        )
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
                                self._bad_request("filename is required")
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
                                "Use multipart/form-data with field 'file', or JSON with filename/text"
                            )
                            return
                        self._ok(api.add_document(filename=filename, text=str(text)), page_index=page_index)
                        return
                    body = self._read_json()
                    page_index = self._page_index_from_body(body)
                    if path == "/query":
                        query = str(body.get("query", "")).strip()
                        if not query:
                            self._bad_request("query is required")
                            return
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
                                self._bad_request("generate_answer must be bool")
                                return
                        else:
                            self._bad_request("generate_answer must be bool")
                            return
                        k = int(body.get("k", 2))
                        threshold_raw = body.get("relevance_threshold")
                        relevance_threshold = (
                            None if threshold_raw is None else float(threshold_raw)
                        )
                        llm_model = str(body.get("llm_model", "")).strip() or None
                        temperature_raw = body.get("temperature", 0.2)
                        max_tokens_raw = body.get("max_tokens")
                        temperature = None if temperature_raw is None else float(temperature_raw)
                        max_tokens = None if max_tokens_raw is None else int(max_tokens_raw)
                        self._ok(
                            api.query(
                                query=query,
                                k=k,
                                relevance_threshold=relevance_threshold,
                                llm_model=llm_model,
                                generate_answer=generate_answer,
                                temperature=temperature,
                                max_tokens=max_tokens,
                            ),
                            page_index=page_index,
                        )
                        return
                    if path == "/kb/document":
                        filename = str(body.get("filename", "")).strip()
                        text = str(body.get("text", ""))
                        if not filename:
                            self._bad_request("filename is required")
                            return
                        self._ok(api.add_document(filename=filename, text=text), page_index=page_index)
                        return
                    if path == "/kb/files":
                        file_paths = body.get("file_paths")
                        if not isinstance(file_paths, list) or not file_paths:
                            self._bad_request("file_paths must be a non-empty list")
                            return
                        self._ok(api.add_files([str(x) for x in file_paths]), page_index=page_index)
                        return
                    if path == "/kb/ingest_dir":
                        root_dir = str(body.get("root_dir", "")).strip()
                        if not root_dir:
                            self._bad_request("root_dir is required")
                            return
                        extensions = body.get("extensions")
                        if extensions is not None and not isinstance(extensions, list):
                            self._bad_request("extensions must be a list")
                            return
                        ext_list = [str(x) for x in extensions] if extensions is not None else None
                        self._ok(api.ingest_dir(root_dir=root_dir, extensions=ext_list), page_index=page_index)
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
                    if path.startswith("/kb/document/"):
                        filename = unquote(path[len("/kb/document/") :]).strip()
                        if not filename:
                            self._bad_request("filename is required")
                            return
                        self._ok(api.remove_document(filename))
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



