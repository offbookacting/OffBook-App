# TODO: This module is fucked up lmao
#  - Lazy loading optional dependencies? Why do we have optional dependencies?
#  - Same typing errors as the rest of the project

# core/pdf_parser.py
from __future__ import annotations
import io
import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

# Optional deps: we import lazily where possible
try:
    import fitz  # PyMuPDF
    _HAVE_PYMUPDF = True
except Exception:
    _HAVE_PYMUPDF = False

try:
    from pypdf import PdfReader
    _HAVE_PYPDF = True
except Exception:
    _HAVE_PYPDF = False

try:
    import pytesseract
    from PIL import Image
    _HAVE_TESSERACT = True
except Exception:
    _HAVE_TESSERACT = False


class PDFParserError(Exception):
    """Generic PDF parsing error."""


@dataclass
class PDFMetadata:
    title: Optional[str]
    author: Optional[str]
    subject: Optional[str]
    creator: Optional[str]
    producer: Optional[str]
    creation_date: Optional[str]
    mod_date: Optional[str]
    num_pages: int
    file_size_bytes: int


@dataclass
class PageText:
    page_index: int   # 0-based
    text: str


class PDFParser:
    """
    Unified PDF parser with:
      - Preferred engine: PyMuPDF (layout-aware, fast)
      - Fallback engine: pypdf
      - Optional OCR per page if text extraction is empty and Tesseract is present
    """

    def __init__(self, pdf_path: str):
        if not os.path.isfile(pdf_path):
            raise PDFParserError(f"PDF not found: {pdf_path}")
        self.pdf_path = pdf_path
        self._doc_pymupdf = None
        self._doc_pypdf = None

        if not (_HAVE_PYMUPDF or _HAVE_PYPDF):
            raise PDFParserError("No PDF backend available. Install 'pymupdf' or 'pypdf'.")

        if _HAVE_PYMUPDF:
            try:
                self._doc_pymupdf = fitz.open(self.pdf_path)
            except Exception as e:
                # If PyMuPDF fails, we’ll fall back to pypdf later
                self._doc_pymupdf = None

        if self._doc_pymupdf is None and _HAVE_PYPDF:
            try:
                self._doc_pypdf = PdfReader(self.pdf_path)
            except Exception as e:
                raise PDFParserError(f"Failed to open PDF with both engines: {e}")

    # ---------- Metadata ----------
    def get_metadata(self) -> PDFMetadata:
        size = os.path.getsize(self.pdf_path)

        if self._doc_pymupdf is not None:
            md = self._doc_pymupdf.metadata or {}
            return PDFMetadata(
                title=md.get("title"),
                author=md.get("author"),
                subject=md.get("subject"),
                creator=md.get("creator"),
                producer=md.get("producer"),
                creation_date=md.get("creationDate") or md.get("creation_date"),
                mod_date=md.get("modDate") or md.get("mod_date"),
                num_pages=self._doc_pymupdf.page_count,
                file_size_bytes=size,
            )

        # pypdf fallback
        info = self._doc_pypdf.metadata or {}
        return PDFMetadata(
            title=str(info.title) if info.title else None,
            author=str(info.author) if info.author else None,
            subject=str(info.subject) if info.subject else None,
            creator=str(info.creator) if info.creator else None,
            producer=str(info.producer) if info.producer else None,
            creation_date=str(info.creation_date) if getattr(info, "creation_date", None) else None,
            mod_date=str(info.modification_date) if getattr(info, "modification_date", None) else None,
            num_pages=len(self._doc_pypdf.pages),
            file_size_bytes=size,
        )

    # ---------- Page count ----------
    def num_pages(self) -> int:
        if self._doc_pymupdf is not None:
            return self._doc_pymupdf.page_count
        return len(self._doc_pypdf.pages)

    # ---------- Text extraction (full) ----------
    def extract_text(
        self,
        preserve_layout: bool = True,
        ocr_if_empty: bool = True,
        ocr_lang: str = "eng",
    ) -> str:
        """
        Extract full-document text. Attempts layout-preserving modes when available.
        OCR kicks in per-page if no text is found and Tesseract is installed.
        """
        pages = self.extract_pages(
            preserve_layout=preserve_layout,
            ocr_if_empty=ocr_if_empty,
            ocr_lang=ocr_lang,
        )
        # Join with double line breaks to clearly separate page boundaries
        return "\n\n".join(p.text for p in pages)

    # ---------- Text extraction (per page) ----------
    def extract_pages(
        self,
        preserve_layout: bool = True,
        ocr_if_empty: bool = True,
        ocr_lang: str = "eng",
    ) -> List[PageText]:
        results: List[PageText] = []

        if self._doc_pymupdf is not None:
            for i in range(self._doc_pymupdf.page_count):
                page = self._doc_pymupdf.load_page(i)
                # PyMuPDF text options: "text", "blocks", "xml", "html"
                # "text" preserves line breaks reasonably; "blocks" allows custom reflow.
                text = page.get_text("text") if preserve_layout else page.get_text()
                if not text.strip() and ocr_if_empty:
                    text = self._ocr_page_pymupdf(page, lang=ocr_lang)
                results.append(PageText(page_index=i, text=text))
            return results

        # pypdf fallback
        for i, page in enumerate(self._doc_pypdf.pages):
            try:
                # pypdf has limited layout control; we still return line breaks where possible
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if not text.strip() and ocr_if_empty:
                text = self._ocr_page_pypdf(i, lang=ocr_lang)
            results.append(PageText(page_index=i, text=text))
        return results

    # ---------- Page image export for OCR ----------
    def _ocr_page_pymupdf(self, page, lang: str = "eng") -> str:
        if not _HAVE_TESSERACT:
            return ""
        # Render page to pixmap -> PIL Image -> Tesseract
        try:
            pix = page.get_pixmap(dpi=300)  # 300 DPI for better OCR
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            return pytesseract.image_to_string(img, lang=lang)
        except Exception:
            return ""

    def _ocr_page_pypdf(self, page_index: int, lang: str = "eng") -> str:
        if not _HAVE_TESSERACT or not _HAVE_PYMUPDF:
            # For OCR from pypdf path, we need PyMuPDF to render
            return ""
        try:
            with fitz.open(self.pdf_path) as d:
                page = d.load_page(page_index)
                return self._ocr_page_pymupdf(page, lang=lang)
        except Exception:
            return ""

    # ---------- Quick helpers ----------
    def page_text(self, page_index: int, **kwargs) -> str:
        """
        Extract a single page's text. kwargs mirror extract_pages parameters.
        """
        pages = self.extract_pages(**kwargs)
        for p in pages:
            if p.page_index == page_index:
                return p.text
        raise PDFParserError(f"Page index out of range: {page_index}")

    def page_images_count(self, page_index: int) -> int:
        """
        Returns image count on a page (PyMuPDF only). 0 if unavailable.
        """
        if self._doc_pymupdf is None:
            return 0
        page = self._doc_pymupdf.load_page(page_index)
        return len(page.get_images(full=True) or [])

    def is_likely_scanned(self, sampling: int = 5) -> bool:
        """
        Heuristic: sample up to 'sampling' pages; if many pages have empty text but images present,
        treat as likely scanned.
        """
        n = self.num_pages()
        if n == 0:
            return False
        indices = list(range(0, n, max(1, n // max(1, sampling))))[:sampling]
        empty_text = 0
        img_pages = 0
        for i in indices:
            txt = self.page_text(i, preserve_layout=True, ocr_if_empty=False).strip()
            if txt == "":
                empty_text += 1
            if self.page_images_count(i) > 0:
                img_pages += 1
        return empty_text >= max(1, len(indices) // 2) and img_pages >= max(1, len(indices) // 2)

    def close(self):
        try:
            if self._doc_pymupdf is not None:
                self._doc_pymupdf.close()
        except Exception:
            pass
        # pypdf uses lazy file handles; nothing explicit to close