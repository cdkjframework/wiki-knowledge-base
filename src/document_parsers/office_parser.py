import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    import doc2txt  # pyright: ignore[reportMissingImports]
except Exception:  # pragma: no cover
    doc2txt = None

try:
    import pythoncom
except Exception:  # pragma: no cover
    pythoncom = None

try:
    import win32com.client as win32_client
except Exception:  # pragma: no cover
    win32_client = None

try:
    from docx2pdf import convert as docx2pdf_convert
except Exception:  # pragma: no cover
    docx2pdf_convert = None

try:
    from tabulate import tabulate as render_tabulate
except Exception:  # pragma: no cover
    render_tabulate = None

from .base import BaseDocumentParser, Document


class OfficeDocumentParser(BaseDocumentParser):
    def _convert_word_to_pdf(self, src_path: Path, out_pdf: Path) -> bool:
        self._logger.info("Word->PDF 开始: source=%s target=%s", src_path, out_pdf)
        if os.name == "nt":
            com_inited = False
            word_app = None
            try:
                self._logger.info("Word->PDF 尝试转换器=win32com")
                if pythoncom is None or win32_client is None:
                    raise ImportError("pywin32 is unavailable")
                pythoncom.CoInitialize()
                com_inited = True
                word_app = win32_client.DispatchEx("Word.Application")
                word_app.Visible = False
                word_app.DisplayAlerts = 0
                doc = None
                try:
                    doc = word_app.Documents.Open(str(src_path), ReadOnly=True)
                    doc.SaveAs(str(out_pdf), FileFormat=17)
                finally:
                    if doc is not None:
                        try:
                            doc.Close(False)
                        except Exception:
                            pass
                    if word_app is not None:
                        try:
                            word_app.Quit()
                        except Exception:
                            pass
                if out_pdf.exists() and out_pdf.stat().st_size > 0:
                    self._logger.info("Word->PDF 成功: converter=win32com output=%s size=%s", out_pdf, out_pdf.stat().st_size)
                    return True
            except Exception as exc:
                self._logger.warning("Word->PDF 失败: converter=win32com source=%s error=%s", src_path, exc)
            finally:
                if pythoncom is not None and com_inited:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
        try:
            self._logger.info("Word->PDF 尝试转换器=docx2pdf")
            if callable(docx2pdf_convert):
                docx2pdf_convert(str(src_path), str(out_pdf))
                if out_pdf.exists() and out_pdf.stat().st_size > 0:
                    self._logger.info("Word->PDF 成功: converter=docx2pdf output=%s size=%s", out_pdf, out_pdf.stat().st_size)
                    return True
            else:
                raise ImportError("docx2pdf is unavailable")
        except Exception as exc:
            self._logger.warning("Word->PDF 失败: converter=docx2pdf source=%s error=%s", src_path, exc)
        try:
            self._logger.info("Word->PDF 尝试转换器=soffice")
            out_dir = out_pdf.parent
            result = subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(src_path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode == 0 and out_pdf.exists() and out_pdf.stat().st_size > 0:
                self._logger.info("Word->PDF 成功: converter=soffice output=%s size=%s", out_pdf, out_pdf.stat().st_size)
                return True
            self._logger.warning(
                "Word->PDF 失败: converter=soffice source=%s returncode=%s stderr=%s",
                src_path,
                result.returncode,
                (result.stderr or "").strip()[:300],
            )
        except Exception as exc:
            self._logger.warning("Word->PDF 失败: converter=soffice source=%s error=%s", src_path, exc)
        self._logger.warning("Word->PDF 所有转换器均失败: source=%s", src_path)
        return False

    def _read_word_via_pdf_marker(self, path: Path) -> str:
        self._logger.info("Word->PDF->Marker 流程开始: source=%s", path)
        with tempfile.TemporaryDirectory(prefix="word_to_pdf_") as tmp_dir:
            pdf_path = Path(tmp_dir) / (path.stem + ".pdf")
            ok = self._convert_word_to_pdf(path, pdf_path)
            if not ok:
                self._logger.warning("Word->PDF->Marker 中止: PDF 转换失败 source=%s", path)
                return ""
            self._logger.info("Word->PDF->Marker 读取转换后 PDF: %s", pdf_path)
            text = self._read_pdf_with_marker(pdf_path)
            if text.strip():
                self._logger.info("Word->PDF->Marker 成功: source=%s extracted_length=%s", path, len(text))
                return text
            self._logger.warning("Word->PDF->Marker 失败: Marker 返回空内容 source=%s", path)
        return ""

    def read_docx(self, path: Path) -> str:
        if Document is None:
            return ""
        blocks_in_order = self._extract_docx_blocks_in_order(path)
        if blocks_in_order:
            lines: list[str] = []
            table_idx = 0
            for block in blocks_in_order:
                b_type = str(block.get("type") or "")
                if b_type == "text":
                    txt = str(block.get("content") or "").strip()
                    if txt:
                        lines.append(txt)
                    continue
                if b_type == "table":
                    table_data = block.get("content") or []
                    md = self._render_complex_table_as_markdown(table_data)
                    if md.strip():
                        table_idx += 1
                        lines.append(f"### 表格 {table_idx}")
                        lines.append(md)
            if lines:
                return "\n\n".join(lines)
        try:
            doc = Document(str(path))
        except Exception:
            return ""
        lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        complex_tables: list[str] = []
        for idx in range(len(doc.tables)):
            data = self._extract_complex_table_data(path, idx)
            if not data:
                continue
            md = self._render_complex_table_as_markdown(data)
            if md.strip():
                complex_tables.append(f"### 表格 {idx + 1}\n\n{md}")
        if complex_tables:
            lines.append("## 表格")
            lines.extend(complex_tables)
        else:
            table_md = self._extract_docx_tables_markdown(path)
            if table_md.strip():
                lines.append("## 表格")
                lines.append(table_md)
        return "\n\n".join(lines)

    def read_doc(self, path: Path) -> str:
        try:
            extract_text = getattr(doc2txt, "extract_text", None) if doc2txt is not None else None
            if not callable(extract_text):
                raise AttributeError("doc2txt.extract_text is unavailable")
            text = str(extract_text(str(path), optimize_format=True) or "")
            if text.strip():
                self._logger.info("[doc2txt] .doc 文档解析成功: %s", path)
                return text
        except Exception as e:
            self._logger.warning("[doc2txt] .doc 文档解析失败，尝试其他方式: %s", e)
        text = self.read_docx(path)
        if text.strip():
            self._logger.info("[docx] .doc 文档用 docx 解析成功: %s", path)
            return text
        self._logger.warning(".doc 文档解析均失败，回退二进制字符串: %s", path)
        return self.read_binary_strings(path)

    def read_excel(self, path: Path) -> str:
        if pd is None:
            return self.read_binary_strings(path)
        try:
            sheets = pd.read_excel(path, sheet_name=None, header=None)
        except Exception:
            return self.read_binary_strings(path)
        rows = []
        for sheet_name, df in sheets.items():
            rows.append(f"# Sheet: {sheet_name}")
            data_rows = df.fillna("").astype(str).values.tolist()
            if not data_rows:
                continue
            if callable(render_tabulate):
                try:
                    md_table = render_tabulate(data_rows, headers="firstrow", tablefmt="pipe")
                    if str(md_table).strip():
                        rows.append(str(md_table))
                        continue
                except Exception:
                    pass
            for row in data_rows:
                vals = [x.strip() for x in row if x and x.strip()]
                if vals:
                    rows.append(" | ".join(vals))
        return "\n".join(rows)

    def read_ofd(self, path: Path) -> str:
        if not zipfile.is_zipfile(path):
            return self.read_binary_strings(path)
        texts = []
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for name in zf.namelist():
                    lower = name.lower()
                    if not lower.endswith(".xml"):
                        continue
                    try:
                        data = zf.read(name)
                    except Exception:
                        continue
                    txt = self.extract_text_from_xml_bytes(data)
                    if txt.strip():
                        texts.append(txt)
        except Exception:
            return self.read_binary_strings(path)
        return "\n".join(texts)

    def read_pws(self, path: Path) -> str:
        if zipfile.is_zipfile(path):
            return self.read_ofd(path)
        return self.read_binary_strings(path)