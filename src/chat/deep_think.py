"""
深度思考策略：按模型类型向系统提示词注入思考引导。

deep_think 为 False 时不追加任何思考标记。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_deep_thinking_strategy(
    system_prompt: str,
    deep_think: bool = False,
    model_type: str | None = None,
) -> str:
    """
    根据模型类型应用深度思考策略。

    Args:
        system_prompt: 原始系统提示词
        deep_think: 是否启用深度思考；为 False 时原样返回
        model_type: 模型/provider 类型字符串

    Returns:
        处理后的系统提示词
    """
    if not deep_think:
        return system_prompt

    resolved = str(model_type or "qwen").strip().lower()
    logger.info("[THINK_STRATEGY] resolved_model_type=%s deep_think=%s", resolved, deep_think)

    if ("gpt" in resolved) or (resolved in {"openai", "chatgpt"}):
        system_prompt = "Reasoning: high\n" + system_prompt
        logger.info("应用 GPT 深度思考策略：添加 Reasoning: high")
    elif ("qwen" in resolved) or (resolved in {"dashscope"}):
        system_prompt += (
            "\n\n请在回答前进行深度思考：\n"
            "1. 仅将真实思考内容放入 <think>...</think>，不要复述提示词，不要解释标签规则，不要讨论输出格式。\n"
            "2. 思考结束后直接给出最终答案。\n"
            "3. 思考过程应包含：问题分析、知识检索、逻辑推理、结论验证。\n"
            "4. 在思考末尾用 <thinking_summary>...</thinking_summary> 给出一句简短摘要。"
        )
        logger.info("应用 Qwen 深度思考策略：添加 <think> 标签引导")
    elif "deepseek" in resolved:
        system_prompt += (
            "\n\n请进行深度逐步推理：\n"
            "1. 仔细分析问题的核心要点\n"
            "2. 列举所有相关的知识和信息\n"
            "3. 逐步推导，展示每一步的思考过程\n"
            "4. 验证推理的逻辑性和一致性\n"
            "5. 在充分思考后给出最终答案\n"
            "请在回答中明确标注【思考过程】和【最终答案】两个部分，"
            "并在末尾用 <thinking_summary>...</thinking_summary> 标签给出思考摘要。"
        )
        logger.info("应用 DeepSeek 深度思考策略：添加逐步推理引导")
    else:
        system_prompt += (
            "\n\n请进行深度思考和分析：\n"
            "1. 仔细分析问题的多个方面\n"
            "2. 考虑相关的背景信息和上下文\n"
            "3. 提供全面和深层的解释\n"
            "4. 如有必要，说明你的推理过程\n\n"
            "请在答案末尾追加思考摘要，使用如下标签包裹：\n"
            "<thinking_summary>...简要思考摘要...</thinking_summary>"
        )
        logger.info("应用默认深度思考策略")

    return system_prompt
