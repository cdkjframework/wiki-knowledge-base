import tempfile
from pathlib import Path

from .base import BaseDocumentParser


class GenericDocumentParser(BaseDocumentParser):
    def convert_file_to_markdown(self, path: Path) -> str:
        if self._markitdown is None:
            return ""
        try:
            result = self._markitdown.convert(str(path))
            text = self._pick_markdown_text(result)
            if path.suffix.lower() == ".docx":
                text = self._merge_docx_table_markdown(path, text)
            if text.strip():
                return text
        except Exception as exc:
            self._logger.debug("MarkItDown 转换失败: %s, error=%s", path, exc)
        return ""

    def extract_text(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in self.WORD_EXTENSIONS:
            text = self.read_docx(path) if ext == ".docx" else self.read_doc(path)
            self._log_extracted_text(f"file:{path}", text)
            return text
        if ext in self.IMAGE_EXTENSIONS:
            image_text = self.read_image_table(path)
            if image_text.strip():
                self._log_extracted_text(f"file:{path}", image_text)
                return image_text
        md_text = self.convert_file_to_markdown(path)
        if md_text.strip():
            self._log_extracted_text(f"file:{path}", md_text)
            return md_text
        text = self._extract_text_fallback(path)
        self._log_extracted_text(f"file:{path}", text)
        return text

    def _extract_text_fallback(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in self.TEXT_EXTENSIONS:
            return self.read_text(path)
        if ext in self.WORD_EXTENSIONS:
            return self.read_docx(path) if ext == ".docx" else self.read_doc(path)
        if ext in self.IMAGE_EXTENSIONS:
            return self.read_image_table(path)
        if ext == ".pdf":
            return self.read_pdf(path)
        if ext == ".ofd":
            return self.read_ofd(path)
        if ext in {".xls", ".xlsx", ".xlsm"}:
            return self.read_excel(path)
        if ext in {".wps"}:
            return self.read_doc(path)
        if ext in {".pws"}:
            return self.read_pws(path)
        return self.read_binary_strings(path)

    def extract_uploaded_file_text(
        self,
        filename: str,
        content: bytes,
        encoding: str | None = None,
        temp_dir: Path | None = None,
    ) -> str:
        data = bytes(content or b"")
        if not data:
            return ""
        ext = Path(filename).suffix.lower()
        if encoding is not None or ext in self.TEXT_EXTENSIONS:
            text = self.decode_uploaded_text_bytes(data, encoding=encoding)
            self._log_extracted_text(f"upload:{filename}", text)
            return text
        text = ""
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=(ext or ".bin"),
                dir=str(temp_dir) if temp_dir is not None else None,
                delete=False,
            ) as fp:
                fp.write(data)
                tmp_path = Path(fp.name)
            md_text = self.convert_file_to_markdown(tmp_path)
            if md_text.strip():
                self._log_extracted_text(f"upload:{filename}", md_text)
                return md_text
            text = self._extract_text_fallback(tmp_path)
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except Exception as exc:
                    self._logger.debug("清理上传临时文件失败: %s", exc)
        if not (text or "").strip():
            text = self.decode_uploaded_text_bytes(data, encoding=encoding)
        self._log_extracted_text(f"upload:{filename}", text)
        return text