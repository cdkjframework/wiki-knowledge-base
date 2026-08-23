"""
商业版专属能力隔离包。

社区产物仅保留门控（edition / cli）；业务实现位于 commercial.business，
由 scripts/build_edition.py 在社区暂存树中物理排除。
"""

from .edition import (
    feature_enabled,
    get_edition,
    is_commercial,
    ocr_allowed,
    require_commercial,
    semantic_chunking_allowed,
)

__all__ = [
    "feature_enabled",
    "get_edition",
    "is_commercial",
    "ocr_allowed",
    "require_commercial",
    "semantic_chunking_allowed",
]
