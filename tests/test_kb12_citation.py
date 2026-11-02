"""KB-12 引用归因：上下文编号、提示词标注要求、来源名次与答案角标同序。"""

from __future__ import annotations

import re
import unittest


def _api():
    from src.api.http_server import KnowledgeBaseApi

    api = object.__new__(KnowledgeBaseApi)
    api._chat_cfg = {}
    return api


class CitationPromptTests(unittest.TestCase):
    def test_context_numbered_and_prompt_requires_markers(self) -> None:
        api = _api()
        results = [
            {"filename": "甲.pdf", "text": "第一段内容", "score": 0.9},
            {"filename": "乙.docx", "text": "第二段内容", "score": 0.8},
        ]
        system_prompt, user_prompt = api._build_chat_prompts("问题", results)
        # 上下文按 [1] [2] 编号，与前端来源卡顺序一致
        self.assertIn("[1] 甲.pdf", user_prompt)
        self.assertIn("[2] 乙.docx", user_prompt)
        # 提示词须要求标注且编号不得编造
        joined = system_prompt + user_prompt
        self.assertIn("标注来源编号", joined)
        self.assertIn("不得编造", joined)

    def test_source_ranks_align_with_answer_markers(self) -> None:
        from src.api.http_server import KnowledgeBaseApi

        items = [
            {"filename": "a", "similarity": 0.5},
            {"filename": "b", "similarity": 0.9},
            {"filename": "c", "similarity": 0.7},
        ]
        KnowledgeBaseApi._assign_source_ranks(items)
        ranks = [it["rank"] for it in items]
        # 名次 1..n 完整且不重复，前端 [n] 角标按列表顺序定位第 n-1 张卡
        self.assertEqual(sorted(ranks), [1, 2, 3])
        answer = "结论见 [1] 与 [3]。"
        markers = [int(x) for x in re.findall(r"\[(\d+)\]", answer)]
        self.assertTrue(all(1 <= m <= len(items) for m in markers))


if __name__ == "__main__":
    unittest.main()
