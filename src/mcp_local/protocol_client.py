import json
import os
from typing import Any, Dict, List, Tuple

import anyio
import httpx

try:
    from mcp import ClientSession, StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    MCP_SDK_AVAILABLE = True
except Exception:
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    streamablehttp_client = None
    MCP_SDK_AVAILABLE = False


class McpProtocolDispatcher:
    def __init__(self, timeout: float = 30.0):
        self.timeout = float(timeout or 30.0)

    def dispatch_http(
        self,
        method: str,
        url: str,
        headers: Dict[str, Any],
        query_params: Dict[str, Any],
        body: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        request_kwargs: Dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "params": query_params,
            "timeout": self.timeout,
        }
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            request_kwargs["json"] = body or {}
        with httpx.Client() as client:
            response = client.request(**request_kwargs)
        response_json, response_text = self._parse_http_response(response)
        return {
            "ok": response.is_success,
            "status_code": response.status_code,
            "request": {
                "transport_type": "http",
                "method": method,
                "url": url,
                "headers": headers,
                "query_params": query_params,
                "body": body if method in {"POST", "PUT", "PATCH", "DELETE"} else None,
            },
            "response_headers": dict(response.headers),
            "response_json": response_json,
            "response_text": response_text,
        }

    def dispatch_streamable_http(
        self,
        url: str,
        tool_name: str,
        headers: Dict[str, Any],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not MCP_SDK_AVAILABLE:
            raise RuntimeError("未安装 mcp SDK，请执行: pip install mcp")
        rpc_headers = {str(key): str(value) for key, value in dict(headers).items()}
        init_payload, call_payload, session_id = anyio.run(
            self._dispatch_streamable_http_with_sdk,
            url,
            rpc_headers,
            tool_name,
            body or {},
        )
        result_payload = call_payload.get("structuredContent")
        if result_payload is None:
            result_payload = call_payload
        error_payload = call_payload if call_payload.get("isError") else None
        return {
            "ok": not call_payload.get("isError", False),
            "status_code": 200,
            "request": {
                "transport_type": "streamable_http",
                "url": url,
                "headers": {key: value for key, value in rpc_headers.items() if key.lower() != "authorization"},
                "tool_name": tool_name,
                "arguments": body or {},
            },
            "response_headers": {},
            "response_json": {
                "initialize": init_payload,
                "call": result_payload,
            },
            "response_text": None,
            "session_id": session_id or None,
            "error": error_payload,
        }

    def dispatch_stdio(
        self,
        command: str,
        command_args: List[str],
        working_directory: str | None,
        env_vars: Dict[str, Any],
        tool_name: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not command:
            raise RuntimeError("stdio 类型 MCP 需要配置 command")
        if not MCP_SDK_AVAILABLE:
            raise RuntimeError("未安装 mcp SDK，请执行: pip install mcp")
        env = {**os.environ, **{str(k): str(v) for k, v in dict(env_vars or {}).items()}} if env_vars else None
        init_payload, call_payload = anyio.run(
            self._dispatch_stdio_with_sdk,
            command,
            command_args or [],
            working_directory,
            env,
            tool_name,
            body or {},
        )
        result_payload = call_payload.get("structuredContent")
        if result_payload is None:
            result_payload = call_payload
        error_payload = call_payload if call_payload.get("isError") else None
        return {
            "ok": not call_payload.get("isError", False),
            "status_code": 0,
            "request": {
                "transport_type": "stdio",
                "command": command,
                "command_args": command_args or [],
                "working_directory": working_directory,
                "tool_name": tool_name,
                "arguments": body or {},
            },
            "response_headers": {},
            "response_json": {
                "initialize": init_payload,
                "call": result_payload,
            },
            "response_text": None,
            "error": error_payload,
        }

    async def _dispatch_streamable_http_with_sdk(
        self,
        url: str,
        headers: Dict[str, str],
        tool_name: str,
        body: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str | None]:
        async with streamablehttp_client(url=url, headers=headers, timeout=self.timeout) as (
            read_stream,
            write_stream,
            get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await session.initialize()
                call_result = await session.call_tool(name=tool_name, arguments=body)
                session_id = get_session_id() if callable(get_session_id) else None
                return (
                    self._model_to_dict(init_result),
                    self._model_to_dict(call_result),
                    session_id,
                )

    async def _dispatch_stdio_with_sdk(
        self,
        command: str,
        command_args: List[str],
        working_directory: str | None,
        env: Dict[str, str] | None,
        tool_name: str,
        body: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        params = StdioServerParameters(
            command=command,
            args=[str(item) for item in command_args],
            env=env,
            cwd=working_directory or None,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await session.initialize()
                call_result = await session.call_tool(name=tool_name, arguments=body)
                return (
                    self._model_to_dict(init_result),
                    self._model_to_dict(call_result),
                )

    @staticmethod
    def _model_to_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if hasattr(value, "model_dump"):
            try:
                data = value.model_dump(mode="json", exclude_none=True)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        if isinstance(value, dict):
            return value
        return {"value": str(value)}

    @staticmethod
    def _parse_http_response(response: httpx.Response) -> Tuple[Any, str | None]:
        content_type = str(response.headers.get("content-type") or "").lower()
        response_json = None
        response_text = None
        if "application/json" in content_type:
            try:
                response_json = response.json()
            except Exception:
                response_text = response.text[:4000]
        else:
            response_text = response.text[:4000]
        return response_json, response_text

    @staticmethod
    def _encode_frame(message: Dict[str, Any]) -> bytes:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        return header + body

    @staticmethod
    def _decode_frames(raw: bytes) -> List[Dict[str, Any]]:
        offset = 0
        messages: List[Dict[str, Any]] = []
        while offset < len(raw):
            split = raw.find(b"\r\n\r\n", offset)
            if split < 0:
                break
            header_bytes = raw[offset:split]
            offset = split + 4
            length = 0
            for line in header_bytes.decode("ascii", errors="ignore").split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1].strip() or "0")
                    break
            if length <= 0 or offset + length > len(raw):
                break
            body = raw[offset:offset + length]
            offset += length
            try:
                parsed = json.loads(body.decode("utf-8", errors="ignore"))
            except Exception:
                continue
            if isinstance(parsed, dict):
                messages.append(parsed)
        return messages