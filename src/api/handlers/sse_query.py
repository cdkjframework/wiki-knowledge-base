"""
问答 SSE 写出：GET/POST /query?stream=1 共用。
"""

from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def write_query_sse(
    http: Any,
    api: Any,
    *,
    query: str,
    k: int,
    relevance_threshold: float | None,
    llm_model: str | None,
    model_config_id: int | None,
    model_config_name: str | None,
    use_default_model_config: bool,
    generate_answer: bool,
    temperature: float | None,
    max_tokens: int | None,
    user_id: str | None,
    session_id: str | None,
    deep_think: bool,
    enable_mcp_auto: bool,
) -> None:
    """向客户端写出完整的 query SSE 事件流（meta / delta / thinking_delta / done）。"""
    http._send_sse_headers()
    answer_parts: List[str] = []
    try:
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
            enable_mcp_auto=enable_mcp_auto,
        )
        http._send_sse(
            "meta",
            {
                "results": data.get("results", []),
                "session_id": session_id,
                "user_id": user_id,
                "mcp_execution": data.get("mcp_execution"),
            },
        )
        finish_reason = "stop"
        answer_text = ""
        thinking_text = ""
        thinking_summary = data.get("thinking_summary")
        if generate_answer:
            split_state = api._init_stream_split_state()
            thinking_parts: List[str] = []
            for piece in data.get("stream", []):
                text = str(piece or "")
                if not text:
                    continue
                routed = api._feed_stream_split_state(split_state, text)
                for channel, delta_piece in routed:
                    if not delta_piece:
                        continue
                    if deep_think:
                        if channel == "thinking":
                            thinking_parts.append(delta_piece)
                            http._send_sse("thinking_delta", {"delta": delta_piece})
                        else:
                            answer_parts.append(delta_piece)
                            http._send_sse("delta", {"delta": delta_piece})
                    else:
                        if channel == "answer":
                            answer_parts.append(delta_piece)
                            http._send_sse("delta", {"delta": delta_piece})
            final_answer, final_thinking, parsed_summary = api._finalize_stream_split_state(
                split_state, use_mixed_content_heuristic=deep_think
            )
            sent_answer = "".join(answer_parts)
            sent_thinking = "".join(thinking_parts)
            if deep_think and final_thinking and len(final_thinking) > len(sent_thinking):
                tail = final_thinking[len(sent_thinking) :]
                if tail:
                    thinking_parts.append(tail)
                    http._send_sse("thinking_delta", {"delta": tail})
            if final_answer and len(final_answer) > len(sent_answer):
                tail = final_answer[len(sent_answer) :]
                if tail:
                    answer_parts.append(tail)
                    http._send_sse("delta", {"delta": tail})
            answer_text = "".join(answer_parts)
            if deep_think:
                thinking_text = "".join(thinking_parts).strip()
                if parsed_summary and not thinking_summary:
                    thinking_summary = parsed_summary
            else:
                thinking_text = ""
                thinking_summary = None
                cleaned = api._strip_non_deep_think_leak(answer_text)
                answer_text = (
                    cleaned.strip() if cleaned.strip() else "抱歉，未能生成最终回答，请重试。"
                )
        else:
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
        http._send_sse(
            "done",
            {
                "answer": answer_text,
                "finish_reason": finish_reason,
                "thinking": thinking_text,
                "thinking_summary": thinking_summary,
                "mcp_execution": data.get("mcp_execution"),
            },
        )
    except Exception as exc:
        logger.exception("SSE stream failed")
        try:
            http._send_sse("error", {"message": str(exc) or "流式问答失败"})
        except Exception:
            pass
    finally:
        try:
            http.close_connection = True
        except Exception:
            pass
