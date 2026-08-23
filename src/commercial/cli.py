"""
wiki-edition 命令行：检查当前版本与功能开关。

用法：
  python -m src.commercial.cli --check
  KB_EDITION=commercial python -m src.commercial.cli --check
"""

from __future__ import annotations

import argparse
import json
import sys

from .edition import (
    COMMERCIAL_FEATURES,
    COMMUNITY_FEATURES,
    feature_enabled,
    get_edition,
    is_commercial,
)


def build_report() -> dict:
    edition = get_edition()
    features = sorted(COMMUNITY_FEATURES | COMMERCIAL_FEATURES)
    return {
        "edition": edition,
        "is_commercial": is_commercial(),
        "features": {fid: feature_enabled(fid) for fid in features},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WIKI KB edition gate checker")
    parser.add_argument(
        "--check",
        action="store_true",
        help="打印当前 edition 与功能开关 JSON",
    )
    args = parser.parse_args(argv)
    if not args.check:
        parser.print_help()
        return 2
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
