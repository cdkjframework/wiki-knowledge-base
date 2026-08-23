"""
HTTP / 业务侧布尔参数解析（含 deep_think）。
"""

from __future__ import annotations

from typing import Any


def parse_bool_param(raw: Any, *, default: bool = False) -> bool:
    """
    将请求中的布尔值规范为 bool。

    Args:
        raw: 原始值（bool/int/str/None）
        default: 无法识别且非非法字符串时的默认值；非法字符串抛 ValueError

    Returns:
        解析后的布尔值

    Raises:
        ValueError: 字符串无法识别为布尔
    """
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        val = raw.strip().lower()
        if val in {"1", "true", "yes", "on"}:
            return True
        if val in {"0", "false", "no", "off", ""}:
            return False
        raise ValueError("必须是布尔值")
    return default


def parse_deep_think(raw: Any) -> bool:
    """
    解析 deep_think；默认关闭。

    Args:
        raw: 请求体或查询参数中的 deep_think

    Returns:
        是否启用深度思考
    """
    return parse_bool_param(raw, default=False)
