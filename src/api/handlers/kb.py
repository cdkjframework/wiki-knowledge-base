"""知识库文档 / 分片相关 HTTP 路由。"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import unquote


def handle_get_kb(http: Any, api: Any, path: str) -> bool:
    """处理 GET /kb/documents、/kb/chunks。"""
    if path == "/kb/documents":
        http._ok(api.list_documents())
        return True

    if path == "/kb/chunks":
        params = http._parse_query_params()
        page_index = http._page_index_from_params(params)
        page_size = 20
        page_size_str = http._get_param_value(params, "pageSize", "")
        if page_size_str:
            try:
                page_size = int(page_size_str)
            except Exception:
                http._bad_request("pageSize 必须是整数")
                return True
        filename = http._get_param_value(params, "filename", "").strip() or None
        query = http._get_param_value(params, "q", "").strip() or None
        http._ok(
            api.list_chunks(
                page_index=page_index,
                page_size=page_size,
                filename=filename,
                query=query,
            ),
            page_index=page_index,
        )
        return True

    return False


def handle_post_kb(http: Any, api: Any, path: str, body: Dict[str, Any] | None = None) -> bool:
    """
    处理 POST /kb/file、/kb/files、/kb/document、/kb/chunks/rebuild。

    /kb/file 与 /kb/files 在调用前尚未读 JSON（可能为 multipart），body 可为 None。
    其余路径要求 body 已解析。
    """
    if path == "/kb/file":
        content_type = http.headers.get("Content-Type", "")
        if "multipart/form-data" in content_type.lower():
            uploaded = http._read_multipart_file("file")
            form = uploaded.get("form", {})
            page_index = http._to_positive_int(form.get("pageIndex", 1), default=1)
            filename = str(form.get("filename") or uploaded.get("filename") or "").strip()
            if not filename:
                http._bad_request("缺少 filename 参数")
                return True
            encoding = str(form.get("encoding", "")).strip() or None
            http._ok(
                api.add_uploaded_file(
                    filename=filename,
                    content=uploaded["content"],
                    encoding=encoding,
                ),
                page_index=page_index,
            )
            return True
        if body is None:
            body = http._read_json()
        page_index = http._page_index_from_body(body)
        filename = str(body.get("filename", "")).strip()
        text = body.get("text")
        if not filename or text is None:
            http._bad_request(
                "请使用 multipart/form-data 并携带 file 字段，或使用 JSON 并提供 filename/text"
            )
            return True
        http._ok(api.add_document(filename=filename, text=str(text)), page_index=page_index)
        return True

    if path == "/kb/files":
        content_type = http.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type.lower():
            http._bad_request("请使用 multipart/form-data 并携带 files 字段")
            return True
        uploaded = http._read_multipart_files("files")
        form = uploaded.get("form", {})
        page_index = http._to_positive_int(form.get("pageIndex", 1), default=1)
        encoding = str(form.get("encoding", "")).strip() or None
        files = uploaded.get("files", [])
        for item in files:
            if not str(item.get("filename") or "").strip():
                http._bad_request("缺少 filename 参数")
                return True
        http._ok(
            api.add_uploaded_files(files=files, encoding=encoding),
            page_index=page_index,
        )
        return True

    if path == "/kb/document":
        if body is None:
            return False
        page_index = http._page_index_from_body(body)
        filename = str(body.get("filename", "")).strip()
        text = str(body.get("text", ""))
        if not filename:
            http._bad_request("缺少 filename 参数")
            return True
        http._ok(api.add_document(filename=filename, text=text), page_index=page_index)
        return True

    if path == "/kb/chunks/rebuild":
        if body is None:
            return False
        page_index = http._page_index_from_body(body)
        filename = str(body.get("filename", "")).strip()
        if not filename:
            http._bad_request("缺少 filename 参数")
            return True
        http._ok(api.rebuild_chunks_for_filename(filename), page_index=page_index)
        return True

    return False


def handle_put_kb(http: Any, api: Any, path: str) -> bool:
    """处理 PUT /kb/chunk/{id}。"""
    if not path.startswith("/kb/chunk/"):
        return False
    chunk_id_raw = unquote(path[len("/kb/chunk/") :]).strip()
    if not chunk_id_raw:
        http._bad_request("缺少 chunk_id 参数")
        return True
    try:
        chunk_id = int(chunk_id_raw)
    except Exception:
        http._bad_request("chunk_id 必须是整数")
        return True
    body = http._read_json()
    page_index = http._page_index_from_body(body)
    text = str(body.get("text", ""))
    if not text.strip():
        http._bad_request("缺少 text 参数")
        return True
    http._ok(api.update_chunk(chunk_id=chunk_id, text=text), page_index=page_index)
    return True


def handle_delete_kb(http: Any, api: Any, path: str) -> bool:
    """处理 DELETE /kb、/kb/document/{name}、/kb/chunk/{id}。"""
    if path == "/kb":
        http._ok(api.clear_knowledge_base())
        return True

    if path.startswith("/kb/document/"):
        filename = unquote(path[len("/kb/document/") :]).strip()
        if not filename:
            http._bad_request("缺少 filename 参数")
            return True
        http._ok(api.remove_document(filename))
        return True

    if path.startswith("/kb/chunk/"):
        chunk_id_raw = unquote(path[len("/kb/chunk/") :]).strip()
        if not chunk_id_raw:
            http._bad_request("缺少 chunk_id 参数")
            return True
        try:
            chunk_id = int(chunk_id_raw)
        except Exception:
            http._bad_request("chunk_id 必须是整数")
            return True
        http._ok(api.delete_chunk(chunk_id))
        return True

    return False
