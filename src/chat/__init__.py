"""
对话与流式问答域（含 deep_think 策略）。

实现渐进从 api/http_server 迁入；当前已落地：
- deep_think.strategy 注入
- 无证据时的确定性拒答文案
"""

from .deep_think import apply_deep_thinking_strategy
from .refusal import INSUFFICIENT_EVIDENCE_ANSWER

__all__ = ["apply_deep_thinking_strategy", "INSUFFICIENT_EVIDENCE_ANSWER"]
