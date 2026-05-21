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

class DoclingParser:
     """Docling PDF parser for scientific document processing."""
     def __init__(self,max_pages: int, max_file_size_mb: int, do_ocr: bool = False, do_table_structure: bool = True):
        """ 
        Initialize DocumentConverter with optimized pipeline options.
        
        :param max_pages: Maximum number of pages to process
        :param max_file_size_mb: Maximum file size in MB
        :param do_ocr: Enable OCR for scanned PDFs (default: False, very slow)
        :param do_table_structure: Extract table structures (default: True)
        """
        
        # Configure pipeline options - 
        pipeline_options = PdfPipelineOptions(
             do_table_structure=do_table_structure,
             do_ocr=do_ocr
        )
        

