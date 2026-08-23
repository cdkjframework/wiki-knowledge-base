import re
import os
from pathlib import Path
from typing import Any, Iterable

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

MarkerPdfConverter = None
create_marker_model_dict = None

try:
    from pix2text import Pix2Text as Pix2TextEngine
except Exception:  # pragma: no cover
    Pix2TextEngine = None

from .base import BaseDocumentParser


def load_marker_pdf_components(model_cache_dir: Path):
    global MarkerPdfConverter, create_marker_model_dict

    marker_cache_dir = Path(model_cache_dir).resolve() / "marker"
    marker_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MODEL_CACHE_DIR"] = str(marker_cache_dir)

    try:
        from surya.settings import settings as surya_settings

        surya_settings.MODEL_CACHE_DIR = str(marker_cache_dir)
    except Exception:
        pass

    if MarkerPdfConverter is not None and create_marker_model_dict is not None:
        return MarkerPdfConverter, create_marker_model_dict, marker_cache_dir

    try:
        from marker.converters.pdf import PdfConverter as marker_pdf_converter
        from marker.models import create_model_dict as create_marker_model_dict_fn
        from surya.settings import settings as surya_settings

        surya_settings.MODEL_CACHE_DIR = str(marker_cache_dir)
        MarkerPdfConverter = marker_pdf_converter
        create_marker_model_dict = create_marker_model_dict_fn
        return MarkerPdfConverter, create_marker_model_dict, marker_cache_dir
    except Exception:
        return None, None, marker_cache_dir


def get_marker_cache_status(model_cache_dir: Path) -> tuple[Path, list[str], list[str]]:
    marker_cache_dir = Path(model_cache_dir).resolve() / "marker"
    components = [
        "layout",
        "text_recognition",
        "text_detection",
        "table_recognition",
        "ocr_error_detection",
    ]
    ready = [name for name in components if (marker_cache_dir / name).exists()]
    missing = [name for name in components if name not in ready]
    return marker_cache_dir, ready, missing


class PdfDocumentParser(BaseDocumentParser):
    def _trace(self, message: str, *args: Any) -> None:
        self._logger.info("[PDF-TRACE] " + message, *args)

    def _read_pdf_with_qwen_ocr_mixed(self, path: Path) -> str:
        self._trace("PDF 混合文本/OCR 解析开始: path=%s", path)
        try:
            if not self._ensure_optional_dependency("fitz", "pymupdf"):
                return ""
            import fitz
            import numpy as np
        except Exception:
            return ""

        has_engine = self._get_qwen_ocr_engine() is not None

        def extract_text_block(block: dict) -> str:
            lines_out: list[str] = []
            for line in block.get("lines", []) or []:
                spans = line.get("spans", []) or []
                line_text = "".join(str(span.get("text", "")) for span in spans if span.get("text")).strip()
                if line_text:
                    lines_out.append(line_text)
            return "\n".join(lines_out).strip()

        def merge_blocks(blocks: list[dict[str, Any]]) -> str:
            usable = [b for b in blocks if str(b.get("text") or "").strip()]
            usable.sort(key=lambda b: (float(b["bbox"][1]), float(b["bbox"][0])))
            return "\n".join(str(b["text"]).strip() for b in usable if str(b["text"]).strip())

        texts: list[str] = []
        with self._open_pdf_with_fitz(path) as doc:
            page_count = doc.page_count
            limit = page_count
            if self._pdf_ocr_max_pages > 0:
                limit = min(page_count, self._pdf_ocr_max_pages)
                if page_count > limit:
                    self._logger.warning("PDF OCR page limit: total=%s limit=%s, path=%s", page_count, limit, path)

            zoom = float(self._pdf_ocr_dpi) / 72.0
            mat = fitz.Matrix(zoom, zoom)

            for idx in range(limit):
                page = doc.load_page(idx)
                page_dict = page.get_text("dict")
                blocks = page_dict.get("blocks", []) or []
                page_blocks: list[dict[str, Any]] = []
                has_text = False
                has_image = False

                for block in blocks:
                    bbox = block.get("bbox")
                    if not bbox or len(bbox) < 4:
                        continue
                    btype = int(block.get("type", 0) or 0)
                    if btype == 0:
                        text_block = extract_text_block(block)
                        if text_block:
                            has_text = True
                            page_blocks.append({"type": "text", "bbox": bbox, "text": text_block})
                    elif btype == 1:
                        has_image = True
                        page_blocks.append({"type": "image", "bbox": bbox, "text": ""})

                if not has_text and has_image:
                    if not has_engine:
                        continue
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = np.frombuffer(pix.samples, dtype=np.uint8)
                    img = img.reshape(pix.height, pix.width, pix.n)
                    if pix.n >= 4:
                        img = img[:, :, :3]
                    page_text = self._qwen_ocr_image(img)
                    if page_text.strip():
                        texts.append(page_text)
                    continue

                if has_text and not has_image:
                    merged = merge_blocks(page_blocks)
                    if merged:
                        texts.append(merged)
                    continue

                if has_text and has_image:
                    if not has_engine:
                        self._logger.warning("PDF mixed text/image but Qwen OCR unavailable; skipped image OCR: %s", path)
                        merged = merge_blocks(page_blocks)
                        if merged:
                            texts.append(merged)
                        continue
                    for block in page_blocks:
                        if block.get("type") != "image":
                            continue
                        rect = fitz.Rect(block["bbox"])
                        rect = rect & page.rect
                        if rect.is_empty:
                            continue
                        pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
                        img = np.frombuffer(pix.samples, dtype=np.uint8)
                        img = img.reshape(pix.height, pix.width, pix.n)
                        if pix.n >= 4:
                            img = img[:, :, :3]
                        block_text = self._qwen_ocr_image(img)
                        if block_text.strip():
                            block["text"] = block_text.strip()
                    merged = merge_blocks(page_blocks)
                    if merged:
                        texts.append(merged)
        return "\n\n".join(t for t in texts if t.strip())

    def _init_marker_pdf_engine(self):
        try:
            if not self._enable_marker:
                if self._marker_config_enabled and not self._marker_cuda_available:
                    self._trace("PDF Marker 已屏蔽: CUDA 不可用，直接回退到 PyMuPDF/PyPDF2")
                else:
                    self._trace("PDF Marker 已通过配置禁用")
                return None
            marker_cache_dir, ready_components, missing_components = get_marker_cache_status(self._model_cache_dir)
            marker_pdf_converter, create_marker_model_dict_fn, marker_cache_dir = load_marker_pdf_components(
                self._model_cache_dir
            )
            if marker_pdf_converter is None or create_marker_model_dict_fn is None:
                raise ImportError("marker is not installed or failed to import at startup")
            self._log_hf_runtime("pdf_marker_init_start")
            self._trace(
                "PDF Marker 初始化开始: cache_dir=%s marker_cache_dir=%s note=%s",
                self._model_cache_dir,
                marker_cache_dir,
                "首次初始化可能触发 Marker 相关模型下载，已强制使用指定目录",
            )
            if missing_components:
                self._trace(
                    "PDF Marker 当前处于模型准备阶段: marker_cache_dir=%s missing_components=%s 如果接下来看到 Downloading *.json/model.safetensors，表示正在下载缺失模型",
                    marker_cache_dir,
                    ", ".join(missing_components),
                )
            else:
                self._trace(
                    "PDF Marker 本地模型已就绪: marker_cache_dir=%s ready_components=%s 接下来若看到 Recognizing Layout / Detecting bboxes / Recognizing Text，均表示识别阶段而非下载阶段",
                    marker_cache_dir,
                    ", ".join(ready_components),
                )
            engine = marker_pdf_converter(artifact_dict=create_marker_model_dict_fn())
            self._trace("PDF Marker 初始化成功: engine=%s", type(engine).__name__)
            return engine
        except Exception as exc:
            self._warn_once("marker_pdf_unavailable", "warning", "PDF Marker 不可用，已回退到当前 PDF 解析器。原因: %s", exc)
            return None

    def _get_marker_pdf_engine(self):
        if not self._marker_pdf_checked:
            self._marker_pdf_checked = True
            self._marker_pdf_engine = self._init_marker_pdf_engine()
        return self._marker_pdf_engine

    def _init_pix2text_engine(self):
        try:
            if not self._enable_pix2text:
                self._trace("Pix2Text 已通过配置禁用")
                return None
            self._patch_optimum_onnxruntime_exports()
            if Pix2TextEngine is None:
                self._warn_once("pix2text_missing_class", "warning", "Pix2Text 模块可导入但未找到 Pix2Text 类，回退到当前图片解析器")
                return None
            self._log_hf_runtime("pix2text_init_start")
            self._trace(
                "Pix2Text 初始化开始: cache_dir=%s note=%s",
                self._model_cache_dir,
                "首次初始化可能触发布局模型下载",
            )
            engine = Pix2TextEngine()
            self._trace("Pix2Text 初始化成功: engine=%s", type(engine).__name__)
            return engine
        except Exception as exc:
            self._warn_once("pix2text_unavailable", "warning", "Pix2Text 不可用，回退到当前图片解析器。原因: %s", exc)
            return None

    def _get_pix2text_engine(self):
        if not self._pix2text_checked:
            self._pix2text_checked = True
            self._pix2text_engine = self._init_pix2text_engine()
        return self._pix2text_engine

    def _init_qwen_ocr_engine(self):
        try:
            import torch
            from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

            device_map = self._ocr_device if self._ocr_device in {"cpu", "cuda", "mps"} else "auto"
            dtype = None
            if self._ocr_dtype in {"float16", "fp16"}:
                dtype = torch.float16
            elif self._ocr_dtype in {"bfloat16", "bf16"}:
                dtype = torch.bfloat16
            elif self._ocr_dtype in {"float32", "fp32"}:
                dtype = torch.float32
            min_pixels = self._ocr_min_pixels if self._ocr_min_pixels > 0 else None
            max_pixels = self._ocr_max_pixels if self._ocr_max_pixels > 0 else None
            self._log_hf_runtime("pdf_qwen_ocr_init_start")
            self._trace(
                "PDF Qwen OCR 初始化开始: model=%s device=%s dtype=%s local_files_only=%s cache_dir=%s",
                self._ocr_model_name,
                device_map,
                self._ocr_dtype,
                True,
                self._model_cache_dir,
            )
            processor = AutoProcessor.from_pretrained(
                self._ocr_model_name,
                min_pixels=min_pixels,
                max_pixels=max_pixels,
                local_files_only=True,
            )
            model = Qwen2VLForConditionalGeneration.from_pretrained(
                self._ocr_model_name,
                torch_dtype=dtype,
                device_map=device_map,
                local_files_only=True,
            )
            model.eval()
            self._trace("PDF Qwen OCR 初始化成功: model=%s", self._ocr_model_name)
            return model, processor
        except Exception as exc:
            self._warn_once("qwen_ocr_unavailable", "warning", "Qwen OCR unavailable: %s", exc)
            return None

    def _get_qwen_ocr_engine(self):
        if not self._qwen_ocr_checked:
            self._qwen_ocr_checked = True
            self._qwen_ocr_engine = self._init_qwen_ocr_engine()
        return self._qwen_ocr_engine

    def _read_pdf_with_pagewise_ocr(self, path: Path) -> tuple[str, bool]:
        self._trace("PDF 页级 OCR 检测开始: path=%s engine=%s", path, self._ocr_parser.engine)
        try:
            import fitz
            import numpy as np
        except Exception as exc:
            self._logger.debug("PyMuPDF unavailable, skip pagewise PDF OCR detection: %s", exc)
            return "", False
        try:
            page_texts: list[str] = []
            used_ocr = False
            with self._open_pdf_with_fitz(path) as doc:
                page_count = doc.page_count
                limit = page_count
                if self._pdf_ocr_max_pages > 0:
                    limit = min(page_count, self._pdf_ocr_max_pages)
                zoom = float(self._pdf_ocr_dpi) / 72.0
                mat = fitz.Matrix(zoom, zoom)
                for idx in range(limit):
                    page = doc.load_page(idx)
                    page_text = (page.get_text("text") or "").strip()
                    if page_text:
                        self._trace("PDF 页级 OCR 跳过页面: page=%s reason=%s", idx + 1, "已存在文本层")
                        page_texts.append(page_text)
                        continue
                    if not page.get_images(full=True):
                        self._trace("PDF 页级 OCR 跳过页面: page=%s reason=%s", idx + 1, "无图片对象")
                        page_texts.append("")
                        continue
                    self._trace("PDF 页级 OCR 执行页面识别: page=%s", idx + 1)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = np.frombuffer(pix.samples, dtype=np.uint8)
                    img = img.reshape(pix.height, pix.width, pix.n)
                    if pix.n >= 4:
                        img = img[:, :, :3]
                    ocr_text = self._ocr_parser.recognize_image(img)
                    page_texts.append(str(ocr_text or "").strip())
                    used_ocr = True
            return "\n\n".join(text for text in page_texts if text.strip()), used_ocr
        except Exception as exc:
            self._logger.debug("Failed to run pagewise PDF OCR detection: %s, error=%s", path, exc)
            return "", False

    def read_pdf(self, path: Path) -> str:
        marker_cache_dir, _, _ = get_marker_cache_status(self._model_cache_dir)
        marker_pdf_converter = None
        create_marker_model_dict_fn = None
        if self._enable_marker:
            marker_pdf_converter, create_marker_model_dict_fn, marker_cache_dir = load_marker_pdf_components(self._model_cache_dir)
        self._trace(
            "PDF 解析开始: path=%s marker_enabled=%s marker_installed=%s marker_cuda_available=%s ocr_enabled=%s ocr_engine=%s cache_dir=%s marker_cache_dir=%s",
            path,
            self._enable_marker,
            bool(marker_pdf_converter is not None and create_marker_model_dict_fn is not None),
            self._marker_cuda_available,
            self._ocr_parser.enabled,
            self._ocr_parser.engine,
            self._model_cache_dir,
            marker_cache_dir,
        )
        self._log_hf_runtime("pdf_read_start")
        marker_text = self._read_pdf_with_marker(path)
        if marker_text.strip() and not self._looks_like_mojibake(marker_text, path):
            self._trace("PDF Marker 解析得到有效文本: path=%s length=%s", path, len(marker_text))
            pagewise_text, used_ocr = ("", False)
            if self._ocr_parser.enabled:
                pagewise_text, used_ocr = self._read_pdf_with_pagewise_ocr(path)
            if used_ocr and pagewise_text.strip():
                self._trace("PDF 最终采用页级 OCR 结果: path=%s", path)
                return pagewise_text
            self._trace("PDF 最终采用 Marker 结果: path=%s", path)
            return marker_text
        if marker_text.strip():
            self._logger.info("PDF text extracted by Marker looks garbled, trying text fallback instead of OCR: %s", path)
        best_text = marker_text if marker_text.strip() else ""
        text = ""
        if PdfReader is not None:
            self._trace("PDF 文本层回退开始: path=%s parser=%s", path, "PyPDF2")
            try:
                reader = PdfReader(str(path))
            except Exception:
                reader = None
            lines = []
            if reader is not None:
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        lines.append(page_text)
            text = "\n".join(lines)
            if text.strip() and not self._looks_like_mojibake(text, path):
                self._trace("PDF 最终采用 PyPDF2 文本层结果: path=%s length=%s", path, len(text))
                return text
        if text.strip():
            best_text = text
        if self._ocr_parser.enabled:
            pagewise_text, used_ocr = self._read_pdf_with_pagewise_ocr(path)
            if used_ocr and pagewise_text.strip():
                self._logger.info("PDF contains image-only pages, using pagewise OCR: %s", path)
                return pagewise_text
        self._trace("PDF 解析结束，返回最佳可用结果: path=%s length=%s", path, len(best_text))
        return best_text

    def _read_pdf_with_marker(self, path: Path) -> str:
        engine = self._get_marker_pdf_engine()
        if engine is None:
            self._trace("PDF Marker 不可用或已禁用，跳过 Marker 解析: path=%s", path)
            return ""
        try:
            marker_cache_dir, ready_components, missing_components = get_marker_cache_status(self._model_cache_dir)
            self._trace("PDF Marker 解析开始: path=%s engine=%s", path, type(engine).__name__)
            if missing_components:
                self._trace(
                    "PDF Marker 解析前仍检测到缺失模型: marker_cache_dir=%s missing_components=%s 若出现 Downloading 日志，属于模型准备阶段",
                    marker_cache_dir,
                    ", ".join(missing_components),
                )
            else:
                self._trace(
                    "PDF Marker 已进入识别阶段: marker_cache_dir=%s ready_components=%s 后续进度条表示版面分析/框检测/OCR 识别，不表示模型下载",
                    marker_cache_dir,
                    ", ".join(ready_components),
                )
            if hasattr(engine, "convert"):
                result = engine.convert(str(path))
            elif hasattr(engine, "__call__"):
                result = engine(str(path))
            else:
                return ""
            text = self._pick_markdown_text(result)
            if text.strip():
                self._trace("PDF Marker 解析完成: path=%s length=%s", path, len(text))
                return text
        except Exception as exc:
            self._logger.debug("PDF Marker 解析失败: %s, error=%s", path, exc)
        return ""

    @staticmethod
    def _clean_ocr_output(output: str, prompt: str) -> str:
        text = (output or "").strip()
        if prompt and text.startswith(prompt):
            text = text[len(prompt) :].strip()
        text = re.sub(r"^(assistant|Assistant|助手)[:：]?\s*", "", text)
        return text.strip()

    def _qwen_ocr_image(self, image: Any) -> str:
        engine = self._get_qwen_ocr_engine()
        if engine is None:
            return ""
        model, processor = engine
        try:
            import numpy as np
            from PIL import Image

            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
        except Exception:
            pass
        try:
            from qwen_vl_utils import process_vision_info
        except Exception:
            return ""
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": self._ocr_prompt}]}]
        prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(text=[prompt], images=image_inputs, videos=video_inputs, return_tensors="pt")
        inputs = inputs.to(model.device)
        outputs = model.generate(**inputs, max_new_tokens=self._ocr_max_new_tokens, do_sample=False)
        decoded = processor.batch_decode(outputs, skip_special_tokens=True)[0]
        return self._clean_ocr_output(decoded, prompt)

    def _open_pdf_with_fitz(self, path: Path):
        import fitz

        try:
            return fitz.open(str(path))
        except Exception:
            data = path.read_bytes()
            return fitz.open(stream=data, filetype="pdf")

    def _render_pdf_pages(self, path: Path) -> Iterable[Any]:
        try:
            if not self._ensure_optional_dependency("fitz", "pymupdf"):
                raise ImportError("PyMuPDF not available")
            import fitz
            import numpy as np

            with self._open_pdf_with_fitz(path) as doc:
                page_count = doc.page_count
                limit = page_count
                if self._pdf_ocr_max_pages > 0:
                    limit = min(page_count, self._pdf_ocr_max_pages)
                    if page_count > limit:
                        self._logger.warning("PDF OCR 页数超限: total=%s limit=%s, path=%s", page_count, limit, path)
                zoom = float(self._pdf_ocr_dpi) / 72.0
                mat = fitz.Matrix(zoom, zoom)
                for idx in range(limit):
                    page = doc.load_page(idx)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = np.frombuffer(pix.samples, dtype=np.uint8)
                    img = img.reshape(pix.height, pix.width, pix.n)
                    if pix.n >= 4:
                        img = img[:, :, :3]
                    yield img
            return
        except Exception as exc:
            self._warn_once("pdf_render_pymupdf_unavailable", "info", "PyMuPDF 渲染 PDF 失败，将尝试其他方案: %s", exc)
        try:
            if not self._ensure_optional_dependency("pdf2image", "pdf2image"):
                raise ImportError("pdf2image not available")
            from pdf2image import convert_from_path
            import numpy as np

            last_page = self._pdf_ocr_max_pages if self._pdf_ocr_max_pages > 0 else None
            pages = convert_from_path(str(path), dpi=self._pdf_ocr_dpi, first_page=1, last_page=last_page)
            for page in pages:
                yield np.array(page)
        except Exception as exc:
            self._warn_once("pdf_render_pdf2image_unavailable", "warning", "pdf2image 渲染 PDF 失败，OCR 无法继续: %s", exc)
            return

    def _read_pdf_with_qwen_ocr(self, path: Path) -> str:
        if self._get_qwen_ocr_engine() is None:
            return ""
        texts: list[str] = []
        try:
            for page_img in self._render_pdf_pages(path):
                page_text = self._qwen_ocr_image(page_img)
                if page_text.strip():
                    texts.append(page_text)
        except Exception as exc:
            self._logger.warning("Qwen OCR 解析 PDF 失败: %s, error=%s", path, exc)
            return ""
        return "\n".join(texts)