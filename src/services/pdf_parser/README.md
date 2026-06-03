# `src/services/pdf_parser/` — PDF parsing

Turns a downloaded PDF on disk into a structured `PdfContent` object
(sections, tables, figures, raw text). Uses **Docling** as the parsing
backend.

---

## Files

```
pdf_parser/
├── docling_parser.py    ← DoclingParser (the actual Docling wrapper)
├── parser.py            ← PDFParserService (the public facade)
└── factory.py           ← make_pdf_parser_service() (cached constructor)
```

| File | Defines | Role |
|---|---|---|
| `docling_parser.py` | `DoclingParser` | Wraps the Docling library; converts a PDF file into a `PdfContent` |
| `parser.py` | `PDFParserService` | Thin facade over `DoclingParser`; the public entry point callers use |
| `factory.py` | `make_pdf_parser_service()` | `@lru_cache` singleton constructor |

---

## How it works

### Two-layer design

```
caller
  ↓
PDFParserService.parse_pdf(pdf_path)        ← public API (parser.py)
  ↓
DoclingParser.parse_pdf(pdf_path)           ← Docling-specific impl (docling_parser.py)
  ↓
PdfContent                                  ← structured output (defined in schemas/)
```

Why split? Because Docling is one of several possible backends. The facade
(`PDFParserService`) lets callers stay unaware of which engine is being
used. Today it always delegates to Docling, but the seam is in place for
later (e.g. PyPDF fallback, OCR-only mode).

### `PDFParserService.parse_pdf` — the public method

```python
async def parse_pdf(self, pdf_path: Path) -> Optional[PdfContent]:
    if not pdf_path.exists():
        raise PDFValidationError(...)
    return self.docling_parser.parse_pdf(pdf_path)
```

Validates the input, delegates to `DoclingParser`, wraps errors into the
project's exception types.

The method is `async def` to fit the orchestrator's concurrent pipeline
(which runs many parses in parallel via `asyncio.gather`), even though
Docling itself is CPU-bound and synchronous. The `await`able interface
matters for composition; the actual parsing runs on the asyncio thread.

### `DoclingParser.parse_pdf` — what Docling does

Docling is a multimodal document-understanding model from IBM. Given a
PDF, it returns:

- **`raw_text`** — the entire flat text.
- **`sections`** — list of `PaperSection(title, content)` — structural
  segmentation (Abstract, Introduction, Method, ...).
- **`tables`** — list of `PaperTable(...)` — extracted tabular data.
- **`figures`** — list of `PaperFigure(...)` — figure references and
  captions.
- **`parser_metadata`** — version info, page count, processing time.

This is the value Docling adds over basic PDF text extraction: it
*understands* the document structure. For RAG, that means you can index
section-by-section and answer questions like "what does this paper's
Method section say?"

### Configurable knobs

`PDFParserService.__init__` takes:

- `max_pages` — skip PDFs longer than this (safety against huge files).
- `max_file_size_mb` — skip PDFs larger than this.
- `do_ocr` — enable OCR for image-based pages (slow; off by default).
- `do_table_structure` — extract table structure vs. just text (on by
  default — useful for arxiv papers).

These all come from `settings.pdf_parser` via the factory.

---

## The factory

```python
@lru_cache(maxsize=1)
def make_pdf_parser_service() -> PDFParserService:
    settings = get_settings()
    return PDFParserService(...)
```

**Critically important to cache this one** — Docling downloads ~1GB of ML
model weights on first init. If you built a fresh parser per Airflow task,
every task would re-download or re-load. With `lru_cache`, the first call
in a process takes minutes, every subsequent call is instant.

This is also why `make_arxiv_client` and the rest use the same pattern —
expensive setup, repeated reuse.

---

## Dependencies

**Imports from:**

- `src.config.PDFParserSettings` — knobs.
- `src.exceptions.PDFParsingException`, `PDFValidationError` — error types.
- `src.schemas.pdf_parser.models.PdfContent` and its sub-types — output
  shapes.
- External: `docling` (the ML library).

**Imported by:**

- `src.services.metadata_fetcher` — calls `parse_pdf()` per downloaded PDF.
- `airflow/dags/arxiv_ingestion/common.py` — calls
  `make_pdf_parser_service()`.

---

## Common questions

**"Why is the first parse so slow?"** — Docling downloads model weights
on first use (one-time, ~1GB). Subsequent parses in the same process are
faster (seconds per paper). The `@lru_cache` factory ensures this happens
exactly once per process.

**"Can I run this on PDFs that aren't from arxiv?"** — Yes. `parse_pdf`
takes any `Path`. There's nothing arxiv-specific in the parser.

**"What if a PDF can't be parsed?"** — `parse_pdf` raises
`PDFValidationError` (file missing) or `PDFParsingException` (Docling
failure). The orchestrator catches these per-paper so one bad PDF doesn't
kill the whole batch.

**"How do I switch to a different parser?"** — Add a new backend
(`pypdf_parser.py`), expose it via `PDFParserService` with a config flag,
choose between them based on settings. The two-layer design exists for
exactly this.
