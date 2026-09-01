"""
商业版本地门控骨架。

通过环境变量 KB_EDITION / WIKI_EDITION 区分 community / commercial。
社区构建不应依赖本包业务能力；本模块仅提供只读门控查询。
"""

from __future__ import annotations

import os
from typing import FrozenSet


COMMUNITY_FEATURES: FrozenSet[str] = frozenset(
    {
        "KB-01",  # 混合检索
        "KB-10",  # 评测集
        "KB-11",  # 指标看板
        "KB-12",  # 引用归因
        "KB-17",  # 查询改写
        "KB-18",  # API Key
        "KB-19",  # 限速
        "KB-20",  # 检索配置
        # 双版「基础能力」默认随社区内核提供，不做商业 flag：
        # KB-08 单 URL / KB-13 基础增量 / KB-15 明文导出
        # （商业增强另走 business/，不进本集合）
    }
)

COMMERCIAL_FEATURES: FrozenSet[str] = frozenset(
    {
        "KB-02",  # 语义递归分片（社区仅为固定长度；本 flag 控制是否走商业实现）
        "KB-03",  # 多租户
        "KB-04",  # RBAC
        "KB-05",  # 审计
        "KB-06",  # 加密
        "KB-07",  # MCP 增强
        "KB-09",  # 连接器
        "KB-14",  # 版本化
        "KB-16",  # OCR（图片 / 扫描件识别；社区仅文字层抽取）
    }
)


def get_edition() -> str:
    """
    读取当前运行版本标识。

    Returns:
        'community' 或 'commercial'
    """
    raw = (
        os.getenv("KB_EDITION")
        or os.getenv("WIKI_EDITION")
        or os.getenv("VITE_EDITION")
        or "community"
    )
    value = str(raw).strip().lower()
    if value in {"commercial", "pro", "enterprise"}:
        return "commercial"
    return "community"


def is_commercial() -> bool:
    """当前是否为商业版运行时。"""
    return get_edition() == "commercial"


def ocr_allowed() -> bool:
    """
    是否允许 OCR（图片 / 扫描 PDF 等视觉识别）。

    社区版只做文字层抽取；OCR 归属商业能力 KB-16。
    """
    return feature_enabled("KB-16")


def semantic_chunking_allowed() -> bool:
    """
    是否使用语义递归分片。

    社区版走固定长度；语义分片归属商业能力 KB-02。
    """
    return feature_enabled("KB-02")


def _license_allows(feature_id: str) -> bool:
    """
    商业能力是否被当前 License 放行。

    社区包没有 business/license：商业 edition 下视为未授权（关）。
    社区 edition 不会走到这里（feature_enabled 已先挡住）。
    """
    # 本地调试：显式旁路（切勿用于生产）
    bypass = str(os.getenv("KB_LICENSE_DEV_BYPASS") or "").strip().lower()
    if bypass in {"1", "true", "yes", "on"}:
        return True
    try:
        from .business.license import license_allows
    except ImportError:
        return False
    return bool(license_allows(feature_id))


def feature_enabled(feature_id: str) -> bool:
    """
    判断功能 ID 是否在当前版本可用。

    Args:
        feature_id: 如 'KB-03'

    Returns:
        社区版仅开放社区能力；商业版还需有效 License 覆盖该能力
    """
    fid = str(feature_id or "").strip().upper()
    if fid in COMMUNITY_FEATURES:
        return True
    if fid in COMMERCIAL_FEATURES:
        if not is_commercial():
            return False
        return _license_allows(fid)
    # 未登记能力：默认关闭（需显式登记）
    return False


def require_commercial(feature_id: str) -> None:
    """
    商业专属能力守卫；社区版或 License 未授权时抛出 PermissionError。

    Args:
        feature_id: 功能编号

    Raises:
        PermissionError: 当前版本无权使用该能力
    """
    if not feature_enabled(feature_id):
        raise PermissionError(
            f"功能 {feature_id} 仅商业版且需有效 License（当前版本={get_edition()}）"
        )


def license_status() -> dict:
    """供 CLI/诊断：社区返回 unavailable；商业返回校验摘要。"""
    if not is_commercial():
        return {"available": False, "edition": "community", "reason": "community_build"}
    try:
        from .business.license import current_status
    except ImportError:
        return {
            "available": False,
            "edition": "commercial",
            "reason": "license_module_missing",
        }
    st = current_status()
    st = dict(st)
    st["available"] = True
    st["edition"] = "commercial"
    return st
