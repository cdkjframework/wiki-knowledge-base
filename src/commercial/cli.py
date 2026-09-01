"""
wiki-edition 命令行：检查版本 / 功能开关 / License；商业可签发证书。

用法：
  python -m src.commercial.cli --check
  KB_EDITION=commercial python -m src.commercial.cli --check
  KB_EDITION=commercial python -m src.commercial.cli --issue --customer Demo --days 365 --cert demo.lic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .edition import (
    COMMERCIAL_FEATURES,
    COMMUNITY_FEATURES,
    feature_enabled,
    get_edition,
    is_commercial,
    license_status,
)


def build_report() -> dict:
    edition = get_edition()
    features = sorted(COMMUNITY_FEATURES | COMMERCIAL_FEATURES)
    return {
        "edition": edition,
        "is_commercial": is_commercial(),
        "features": {fid: feature_enabled(fid) for fid in features},
        "license": license_status(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WIKI KB edition / license gate checker")
    parser.add_argument(
        "--check",
        action="store_true",
        help="打印当前 edition、功能开关与 License 状态 JSON",
    )
    parser.add_argument(
        "--issue",
        action="store_true",
        help="签发 License（需能导入 business.license；建议 KB_EDITION=commercial）",
    )
    parser.add_argument("--customer", default="Demo", help="--issue 时的客户名")
    parser.add_argument("--days", type=int, default=365, help="--issue 有效天数")
    parser.add_argument(
        "--features",
        default="*",
        help="--issue 功能列表，逗号分隔；* 表示全部商业能力",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="--issue 后写入本地 conf/license.key（或 KB_LICENSE_PATH）并立刻生效",
    )
    parser.add_argument(
        "--cert",
        default="",
        help="--issue 时额外写出可下发的证书文件路径（建议 .lic）",
    )
    args = parser.parse_args(argv)

    if args.issue:
        try:
            from .business.license import issue_license, save_raw_key, write_certificate_file
        except ImportError:
            print(
                "[FAIL] 无法导入 commercial.business.license（社区包无此模块）",
                file=sys.stderr,
            )
            return 1
        feats = [p.strip() for p in str(args.features).split(",") if p.strip()]
        key = issue_license(customer=args.customer, days=int(args.days), features=feats)
        result: dict = {"key": key}
        if args.write:
            result["saved"] = str(save_raw_key(key))
        cert_path = str(args.cert or "").strip()
        if cert_path:
            result["certificate"] = str(write_certificate_file(key, Path(cert_path)))
        if args.write or cert_path:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(key)
        return 0

    if not args.check:
        parser.print_help()
        return 2
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
