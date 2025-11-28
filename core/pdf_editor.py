# core/pdf_editor.py
"""
PDF editor component with annotation and editing capabilities.
"""
from __future__ import annotations
import io
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

try:
    import fitz  # PyMuPDF
    _HAVE_PYMUPDF = True
except Exception:
    _HAVE_PYMUPDF = False


class PDFEditorError(Exception):
    pass


@dataclass
class Annotation:
    """Represents a PDF annotation."""
    page: int
    type: str  # "highlight", "note", "text", "drawing", etc.
    rect: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    content: str = ""
    color: Tuple[float, float, float] = (1.0, 1.0, 0.0)  # RGB 0-1
    author: str = "Actor"
    created_at: float = 0.0


class PDFEditor:
    """
    PDF editor with annotation capabilities.
    Can add highlights, notes, text, and drawings to PDFs.
    """
    
    def __init__(self, pdf_path: Union[str, Path]):
        if not _HAVE_PYMUPDF:
            raise PDFEditorError("PyMuPDF is required for PDF editing")
        
        self.pdf_path = Path(pdf_path).expanduser().resolve()
        if not self.pdf_path.exists():
            raise PDFEditorError(f"PDF not found: {self.pdf_path}")
        
        self._doc: Optional[fitz.Document] = None
        self._annotations: List[Annotation] = []
        self._load()
    
    def _load(self) -> None:
        """Load PDF document."""
        try:
            self._doc = fitz.open(str(self.pdf_path))
        except Exception as e:
            raise PDFEditorError(f"Failed to open PDF: {e}")
    
    def close(self) -> None:
        """Close the PDF document."""
        if self._doc:
            self._doc.close()
            self._doc = None
    
    def num_pages(self) -> int:
        """Get number of pages."""
        if not self._doc:
            return 0
        return self._doc.page_count
    
    def get_page_image(self, page_num: int, zoom: float = 2.0) -> Optional[bytes]:
        """
        Get page as image bytes (PNG format).
        Useful for displaying in GUI.
        """
        if not self._doc or page_num < 0 or page_num >= self._doc.page_count:
            return None
        
        page = self._doc[page_num]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    
    def add_highlight(
        self,
        page: int,
        rect: Tuple[float, float, float, float],
        color: Tuple[float, float, float] = (1.0, 1.0, 0.0),
        content: str = ""
    ) -> Annotation:
        """Add a highlight annotation."""
        if not self._doc or page < 0 or page >= self._doc.page_count:
            raise PDFEditorError(f"Invalid page: {page}")
        
        import time
        annotation = Annotation(
            page=page,
            type="highlight",
            rect=rect,
            content=content,
            color=color,
            created_at=time.time(),
        )
        
        # Add annotation to PDF
        page_obj = self._doc[page]
        highlight = page_obj.add_highlight_annot(rect)
        highlight.set_colors(stroke=color)
        highlight.set_info(content=content, title="Highlight")
        highlight.update()
        
        self._annotations.append(annotation)
        return annotation
    
    def add_text_note(
        self,
        page: int,
        point: Tuple[float, float],
        content: str,
        color: Tuple[float, float, float] = (1.0, 1.0, 0.0)
    ) -> Annotation:
        """Add a text note annotation."""
        if not self._doc or page < 0 or page >= self._doc.page_count:
            raise PDFEditorError(f"Invalid page: {page}")
        
        import time
        # Create a small rect for the note icon
        rect = (point[0], point[1], point[0] + 20, point[1] + 20)
        
        annotation = Annotation(
            page=page,
            type="note",
            rect=rect,
            content=content,
            color=color,
            created_at=time.time(),
        )
        
        # Add annotation to PDF
        page_obj = self._doc[page]
        note = page_obj.add_text_annot(point, content)
        note.set_colors(stroke=color)
        note.update()
        
        self._annotations.append(annotation)
        return annotation
    
    def add_text_box(
        self,
        page: int,
        rect: Tuple[float, float, float, float],
        text: str,
        font_size: int = 12
    ) -> Annotation:
        """Add a text box annotation."""
        if not self._doc or page < 0 or page >= self._doc.page_count:
            raise PDFEditorError(f"Invalid page: {page}")
        
        import time
        annotation = Annotation(
            page=page,
            type="text",
            rect=rect,
            content=text,
            created_at=time.time(),
        )
        
        # Add text to PDF page
        page_obj = self._doc[page]
        page_obj.insert_text(
            (rect[0], rect[1]),
            text,
            fontsize=font_size,
            color=(0, 0, 0),
        )
        
        self._annotations.append(annotation)
        return annotation
    
    def get_annotations(self, page: Optional[int] = None) -> List[Annotation]:
        """Get annotations, optionally filtered by page."""
        if page is None:
            return list(self._annotations)
        return [ann for ann in self._annotations if ann.page == page]
    
    def remove_annotation(self, annotation: Annotation) -> None:
        """Remove an annotation."""
        if annotation in self._annotations:
            self._annotations.remove(annotation)
            # Note: Removing from PDF would require tracking annotation objects
    
    def save(self, output_path: Optional[Union[str, Path]] = None) -> None:
        """Save the PDF with annotations."""
        if not self._doc:
            return
        
        output = Path(output_path) if output_path else self.pdf_path
        self._doc.save(str(output), incremental=False, encryption=fitz.PDF_ENCRYPT_KEEP)
    
    def save_copy(self, output_path: Union[str, Path]) -> None:
        """Save a copy of the PDF with annotations."""
        self.save(output_path)
    
    def extract_text_from_rect(
        self,
        page: int,
        rect: Tuple[float, float, float, float]
    ) -> str:
        """Extract text from a specific rectangle on a page."""
        if not self._doc or page < 0 or page >= self._doc.page_count:
            return ""
        
        page_obj = self._doc[page]
        text = page_obj.get_text("text", clip=rect)
        return text.strip()

