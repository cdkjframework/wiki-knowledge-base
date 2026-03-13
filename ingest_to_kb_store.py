#!/usr/bin/env python
"""将单个文档导入知识库并生成 kb_store 向量数据。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.knowledge_base import KnowledgeBase


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest one file into kb_store vector store")
    parser.add_argument("file", help="文档路径，例如: C:/docs/manual.docx")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(json.dumps({"ok": False, "error": f"文件不存在: {file_path}"}, ensure_ascii=False))
        return 1

    try:
        kb = KnowledgeBase()
        chunks = kb.add_text_file(str(file_path))
        stats = kb.stats()
        print(
            json.dumps(
                {
                    "ok": True,
                    "file": str(file_path),
                    "chunks_added": chunks,
                    "kb_store": "./kb_store",
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中断"}, ensure_ascii=False))
        return 130
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
