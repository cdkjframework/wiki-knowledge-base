"""GET/POST /query 路由处理。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..bool_params import parse_bool_param, parse_deep_think
from .sse_query import write_query_sse

logger = logging.getLogger(__name__)


def _last(params: Dict[str, List[str]], key: str) -> str | None:
    vals = params.get(key)
    if not vals:
        return None
    raw = vals[-1]
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def handle_get_query(http: Any, api: Any, path: str) -> bool:
    """处理 GET /query（含 stream SSE）。"""
    if path != "/query":
        return False

    params = http._parse_query_params()
    page_index = http._page_index_from_params(params)
    stream_mode = False
    if "stream" in params and params["stream"]:
        stream_mode = params["stream"][-1].strip().lower() in {"1", "true", "yes", "on"}

    user_id = _last(params, "user_id") or _last(params, "userId")
    session_id = _last(params, "session_id") or _last(params, "sessionId")
    if user_id and not session_id:
        session_id = api._new_session_id(user_id)

    query = _last(params, "query") or ""
    logger.info(
        "HTTP /query GET: stream=%s query_len=%d user_id=%s session_id=%s",
        stream_mode,
        len(query),
        bool(user_id),
        bool(session_id),
    )
    if not query:
        http._bad_request("缺少 query 参数")
        return True

    try:
        k = int(params.get("k", ["2"])[-1])
    except Exception:
        http._bad_request("k 必须是整数")
        return True

    relevance_threshold = None
    if "relevance_threshold" in params and params["relevance_threshold"]:
        try:
            relevance_threshold = float(params["relevance_threshold"][-1])
        except Exception:
            http._bad_request("relevance_threshold 必须是数字")
            return True

    llm_model = _last(params, "llm_model")

    model_config_id = None
    if "model_config_id" in params and params["model_config_id"]:
        try:
            model_config_id = int(params["model_config_id"][-1])
        except Exception:
            http._bad_request("model_config_id 必须是整数")
            return True
    model_config_name = _last(params, "model_config_name")

    use_default_model_config = False
    if "use_default_model_config" in params and params["use_default_model_config"]:
        try:
            use_default_model_config = parse_bool_param(
                params["use_default_model_config"][-1], default=False
            )
        except ValueError:
            http._bad_request("use_default_model_config 必须是布尔值")
            return True

    generate_answer = True
    if "generate_answer" in params and params["generate_answer"]:
        try:
            generate_answer = parse_bool_param(params["generate_answer"][-1], default=True)
        except ValueError:
            http._bad_request("generate_answer 必须是布尔值")
            return True

    deep_think = False
    if "deep_think" in params and params["deep_think"]:
        try:
            deep_think = parse_deep_think(params["deep_think"][-1])
        except ValueError:
            http._bad_request("deep_think 必须是布尔值")
            return True

    temperature = 0.2
    if "temperature" in params and params["temperature"]:
        try:
            temperature = float(params["temperature"][-1])
        except Exception:
            http._bad_request("temperature 必须是数字")
            return True

    max_tokens = api._default_chat_max_tokens()
    if "max_tokens" in params and params["max_tokens"]:
        try:
            max_tokens = int(params["max_tokens"][-1])
        except Exception:
            http._bad_request("max_tokens 必须是整数")
            return True

    enable_mcp_auto = False
    if "enable_mcp_auto" in params and params["enable_mcp_auto"]:
        try:
            enable_mcp_auto = parse_bool_param(params["enable_mcp_auto"][-1], default=False)
        except ValueError:
            http._bad_request("enable_mcp_auto 必须是布尔值")
            return True

    if stream_mode:
        write_query_sse(
            http,
            api,
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
            enable_mcp_auto=enable_mcp_auto,
        )
        return True

    http._ok(
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
            enable_mcp_auto=enable_mcp_auto,
        ),
        page_index=page_index,
    )
    return True


def handle_post_query(http: Any, api: Any, path: str, body: Dict[str, Any]) -> bool:
    """处理 POST /query（含 stream SSE）。body 须已由调用方读入。"""
    if path != "/query":
        return False

    page_index = http._page_index_from_body(body)
    query = str(body.get("query", "")).strip()
    if not query:
        http._bad_request("缺少 query 参数")
        return True

    user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None
    session_id = str(body.get("session_id") or body.get("sessionId") or "").strip() or None
    if user_id and not session_id:
        session_id = api._new_session_id(user_id)

    try:
        generate_answer = parse_bool_param(body.get("generate_answer", True), default=True)
    except ValueError:
        http._bad_request("generate_answer 必须是布尔值")
        return True

    try:
        deep_think = parse_deep_think(body.get("deep_think", False))
    except ValueError:
        http._bad_request("deep_think 必须是布尔值")
        return True

    k = int(body.get("k", 2))
    threshold_raw = body.get("relevance_threshold")
    relevance_threshold = None if threshold_raw is None else float(threshold_raw)
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
    enable_mcp_auto = bool(body.get("enable_mcp_auto", False))
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
        write_query_sse(
            http,
            api,
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
            enable_mcp_auto=enable_mcp_auto,
        )
        return True

    http._ok(
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
            enable_mcp_auto=enable_mcp_auto,
        ),
        page_index=page_index,
    )
    return True
