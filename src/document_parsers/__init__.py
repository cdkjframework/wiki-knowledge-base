from .base import BaseDocumentParser
from .generic_parser import GenericDocumentParser
from .image_parser import ImageDocumentParser
from .office_parser import OfficeDocumentParser
from .ocr_parser import DisabledOcrParser, create_ocr_parser
from .pdf_parser import PdfDocumentParser


class KnowledgeBaseDocumentParser(
    GenericDocumentParser,
    OfficeDocumentParser,
    PdfDocumentParser,
    ImageDocumentParser,
    BaseDocumentParser,
):
    pass

__all__ = [
    "BaseDocumentParser",
    "DisabledOcrParser",
    "GenericDocumentParser",
    "ImageDocumentParser",
    "KnowledgeBaseDocumentParser",
    "OfficeDocumentParser",
    "PdfDocumentParser",
    "create_ocr_parser",
]