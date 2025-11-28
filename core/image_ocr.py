# core/image_ocr.py
"""
OCR utility for extracting text from image files.
Uses EasyOCR which is open source and commercially licensable (Apache 2.0).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Callable
import numpy as np

try:
    import easyocr
    from PIL import Image
    _HAVE_EASYOCR = True
except Exception:
    _HAVE_EASYOCR = False


class ImageOCRError(Exception):
    """Generic OCR error."""


# Global EasyOCR reader instance (lazy initialization)
_reader_instance: Optional[easyocr.Reader] = None


def _get_reader(lang: str = "en") -> easyocr.Reader:
    """Get or create EasyOCR reader instance."""
    global _reader_instance
    if _reader_instance is None:
        if not _HAVE_EASYOCR:
            raise ImageOCRError(
                "EasyOCR is not available. Please install EasyOCR:\n\n"
                "pip install easyocr\n\n"
                "Note: EasyOCR requires PyTorch, which will be installed automatically."
            )
        # Initialize reader (this downloads models on first use)
        _reader_instance = easyocr.Reader([lang], gpu=False)
    return _reader_instance


def extract_text_from_image(
    image_path: Path,
    lang: str = "en",
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> str:
    """
    Extract text from an image file using EasyOCR.
    
    Args:
        image_path: Path to the image file
        lang: Language code for OCR (default: "en" for English)
        progress_callback: Optional callback function(progress, total) for progress updates
        
    Returns:
        Extracted text as a string
        
    Raises:
        ImageOCRError: If OCR fails or EasyOCR is not available
    """
    if not _HAVE_EASYOCR:
        raise ImageOCRError(
            "EasyOCR is not available. Please install EasyOCR:\n\n"
            "pip install easyocr\n\n"
            "Note: EasyOCR requires PyTorch, which will be installed automatically."
        )
    
    if not image_path.exists():
        raise ImageOCRError(f"Image file not found: {image_path}")
    
    try:
        # Report progress start
        if progress_callback:
            progress_callback(0, 100)
        
        # Load image
        if progress_callback:
            progress_callback(10, 100)
        
        img = Image.open(str(image_path))
        
        # Convert to RGB if necessary
        if img.mode != "RGB":
            if progress_callback:
                progress_callback(20, 100)
            img = img.convert("RGB")
        
        # Convert PIL Image to numpy array for EasyOCR
        if progress_callback:
            progress_callback(30, 100)
        
        img_array = np.array(img)
        
        # Get EasyOCR reader
        if progress_callback:
            progress_callback(40, 100)
        
        reader = _get_reader(lang)
        
        # Perform OCR
        if progress_callback:
            progress_callback(50, 100)
        
        # EasyOCR returns list of (bbox, text, confidence) tuples
        results = reader.readtext(img_array)
        
        if progress_callback:
            progress_callback(90, 100)
        
        # Extract text from results, preserving line breaks
        # Sort by vertical position (top to bottom) to maintain reading order
        if results:
            # Sort by top Y coordinate of bounding box
            sorted_results = sorted(results, key=lambda x: x[0][0][1])  # Sort by top-left Y coordinate
            
            # Group by approximate line (similar Y coordinates)
            lines = []
            current_line = []
            current_y = None
            y_threshold = 20  # Pixels - lines within this distance are considered same line
            
            for bbox, text, confidence in sorted_results:
                top_y = bbox[0][1]  # Top-left Y coordinate
                
                if current_y is None or abs(top_y - current_y) > y_threshold:
                    # New line
                    if current_line:
                        lines.append(" ".join(current_line))
                    current_line = [text]
                    current_y = top_y
                else:
                    # Same line
                    current_line.append(text)
            
            # Add last line
            if current_line:
                lines.append(" ".join(current_line))
            
            extracted_text = "\n".join(lines)
        else:
            extracted_text = ""
        
        if progress_callback:
            progress_callback(100, 100)
        
        return extracted_text.strip()
        
    except Exception as e:
        error_msg = str(e)
        if "easyocr" in error_msg.lower() or "not found" in error_msg.lower():
            raise ImageOCRError(
                "EasyOCR is not installed or not working properly.\n\n"
                "Please install EasyOCR:\n\n"
                "pip install easyocr\n\n"
                "Note: EasyOCR requires PyTorch, which will be installed automatically."
            ) from e
        raise ImageOCRError(f"Failed to extract text from image: {e}") from e


def is_image_file(file_path: Path) -> bool:
    """
    Check if a file is an image file that can be processed with OCR.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if the file is an image file
    """
    if not file_path.is_file():
        return False
    
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
    return file_path.suffix.lower() in image_extensions


def has_text_content(file_path: Path) -> bool:
    """
    Check if a file has embedded text content that can be extracted without OCR.
    This does NOT use OCR - it only checks for embedded text in the file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        False if file needs OCR (images or scanned PDFs), True if it has embedded text
    """
    if is_image_file(file_path):
        return False  # Images need OCR - they don't have embedded text
    
    # Check PDFs for embedded text (only check first page for speed)
    if file_path.suffix.lower() == ".pdf":
        try:
            from core.pdf_parser import PDFParser
            parser = PDFParser(str(file_path))
            # Only check first page for speed - this checks for embedded text, NOT metadata
            # This does NOT use OCR
            has_text = parser.has_embedded_text(sampling=1)
            parser.close()
            return has_text
        except Exception:
            # If we can't check, assume it has text (don't force OCR)
            return True
    
    return True  # Other files assumed to have text
