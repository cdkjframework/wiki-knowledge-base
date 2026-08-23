from pathlib import Path

from .base import BaseDocumentParser


class ImageDocumentParser(BaseDocumentParser):
    def read_image_table(self, path: Path) -> str:
        # 图片没有文字层，社区版直接跳过（OCR / Pix2Text 属商业能力）
        if not self._enable_pix2text and not self._ocr_parser.enabled:
            self._logger.info("社区版不支持图片 OCR，跳过: %s", path)
            return ""

        if self._enable_pix2text:
            engine = self._get_pix2text_engine()
            if engine is not None:
                try:
                    for method_name in ("recognize", "recognize_text", "ocr"):
                        method = getattr(engine, method_name, None)
                        if not callable(method):
                            continue
                        result = method(str(path))
                        text = self._pick_markdown_text(result)
                        if text.strip():
                            return text
                except Exception as exc:
                    self._logger.debug("Pix2Text 图片解析失败: %s, error=%s", path, exc)

        if self._ocr_parser.enabled:
            try:
                from PIL import Image

                img = Image.open(str(path))
                text = self._ocr_parser.recognize_image(img)
                if text.strip():
                    return text
            except Exception as exc:
                self._logger.debug("OCR 图片回退失败: %s, error=%s", path, exc)
        return ""