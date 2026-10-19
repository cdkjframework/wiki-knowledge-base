"""
无可靠证据时的确定性拒答。

以前没有来源也照样把提示词丢给生成模型，拒不拒答全看模型听不听话；
现在服务端直接给固定文案，普通和流式两条路径共用这一句，前端也按它识别「答不出」。
"""

from __future__ import annotations

INSUFFICIENT_EVIDENCE_ANSWER = "根据当前知识库无法确定。"
