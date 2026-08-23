"""
对话与流式问答域（含 deep_think 策略）。

实现渐进从 api/http_server 迁入；当前已落地：
- deep_think.strategy 注入
"""

from .deep_think import apply_deep_thinking_strategy

__all__ = ["apply_deep_thinking_strategy"]
