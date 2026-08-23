"""
OCR 桥接层（社区可保留）。

真正的 OCR 引擎在 `commercial.business.ocr`；社区包没有该目录时，
这里返回禁用桩，保证文字层解析链路仍可跑。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional


class DisabledOcrParser:
    """社区版 / 无商业包时的空实现：永远不识别。"""

    enabled = False
    engine = "disabled"

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info("使用 DisabledOcrParser：当前环境不提供 OCR（KB-16）")

    def recognize_image(self, image: Any) -> str:
        return ""

    def recognize_pdf(self, pdf_path: Path) -> str:
        return ""


def create_ocr_parser(
    config: dict,
    model_cache_dir: Path,
    logger: Optional[logging.Logger] = None,
) -> Any:
    """
    按版本创建 OCR 实现。

    - 商业版且装了 business.ocr → 返回真正的 OcrParser
    - 社区版 / ImportError / PermissionError → DisabledOcrParser
    """
    log = logger or logging.getLogger(__name__)
    try:
        from ..commercial.edition import ocr_allowed
    except ImportError:
        try:
            from commercial.edition import ocr_allowed  # type: ignore
        except ImportError:
            try:
                from src.commercial.edition import ocr_allowed  # type: ignore
            except ImportError:
                return DisabledOcrParser(logger=log)

    if not ocr_allowed():
        log.info("社区版或未开放 KB-16：OCR 使用禁用桩")
        return DisabledOcrParser(logger=log)

    try:
        from ..commercial.business.ocr import OcrParser
    except ImportError:
        try:
            from commercial.business.ocr import OcrParser  # type: ignore
        except ImportError:
            try:
                from src.commercial.business.ocr import OcrParser  # type: ignore
            except ImportError:
                log.warning("商业 OCR 包不可用（可能被社区打包剔除），回退禁用桩")
                return DisabledOcrParser(logger=log)

    try:
        return OcrParser(config, model_cache_dir, logger=log)
    except PermissionError:
        log.info("OCR 门控拒绝，回退禁用桩")
        return DisabledOcrParser(logger=log)


# 兼容旧名：外部若仍 from ...ocr_parser import OcrParser，拿到的是工厂创建入口类名易混，
# 推荐改用 create_ocr_parser。这里保留别名指向商业实现（存在时）仅作类型提示弱兼容。
try:
    from ..commercial.business.ocr import OcrParser as OcrParser  # type: ignore
except ImportError:
    try:
        from commercial.business.ocr import OcrParser as OcrParser  # type: ignore
    except ImportError:
        try:
            from src.commercial.business.ocr import OcrParser as OcrParser  # type: ignore
        except ImportError:
            OcrParser = DisabledOcrParser  # type: ignore


__all__ = ["DisabledOcrParser", "OcrParser", "create_ocr_parser"]
