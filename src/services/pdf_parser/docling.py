# pypdfium2 is used to convert pdf pages to images, Extract text and Validate PDFs

import logging
from pathlib import Path
from typing import Optional

import pypdfium2 as pdfium

from docling.datamodel.base_models import InputFormat # Tells Docling what type of file you're giving it — InputFormat.PDF, InputFormat.DOCX etc.
from docling.datamodel.pipeline_options import PdfPipelineOptions # Configuration for how Docling processes the PDF — whether to do OCR, extract tables, extract figures etc. 
from docling.document_converter import DocumentConverter, PdfFormatOption # DocumentConverter is the main class that does all the work
from src.exceptions import PDFParsingException, PDFValidationError
from src.schemas.pdf_parser.models import PaperFigure, PaperSection, PaperTable, ParserType, PdfContent

logger = logging.getLogger(__name__)


