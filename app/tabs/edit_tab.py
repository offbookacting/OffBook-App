# app/tabs/edit_tab.py
"""
Edit tab - allows editing text files in any folder.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLabel, QMessageBox, QToolButton
)
import re

from core.nlp_processor import parse_script_text, ScriptParse
from core.image_ocr import is_image_file, has_text_content


class EditTab(QWidget):
    """Edit tab for editing text files."""
    
    text_changed = pyqtSignal(str)  # emits edited text when saved
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_file_path: Optional[Path] = None
        self.is_modified: bool = False
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        self.lbl_file = QLabel("No file selected")
        toolbar.addWidget(self.lbl_file)
        
        toolbar.addStretch()
        
        # Save button (icon only)
        self.btn_save = QToolButton()
        # Use standard save icon (disk/floppy icon)
        self.btn_save.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_DriveFDIcon))
        self.btn_save.setToolTip("Save")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        toolbar.addWidget(self.btn_save)
        
        layout.addLayout(toolbar)
        
        # Text editor
        self.txt_editor = QTextEdit()
        self.txt_editor.setFontFamily("Courier Prime")
        self.txt_editor.setFontPointSize(12)
        self.txt_editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.txt_editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Set non-white background and black text
        self.txt_editor.setStyleSheet("QTextEdit { background-color: #f8f8f8; color: black; }")
        self.txt_editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.txt_editor, stretch=1)
        
        # Status label
        self.lbl_status = QLabel("Select a text file from the Files tab to edit, or create a new file.")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
    
    def _on_text_changed(self) -> None:
        """Handle text change - mark as modified."""
        if self.current_file_path:
            self.is_modified = True
            self.btn_save.setEnabled(True)
            self.lbl_status.setText("Modified - Click 'Save' to save changes")
    
    def _rtf_to_plain_text_improved(self, rtf_content: str) -> str:
        """
        RTF to plain text conversion.
        Strategy: Skip all RTF control sequences and groups, extract only text content.
        """
        if not rtf_content:
            return ""
        
        text = rtf_content
        result = []
        i = 0
        in_skip_group = False
        skip_group_depth = 0
        
        def skip_header_group(start_pos):
            """Skip a header group starting at start_pos, return position after group."""
            depth = 1
            j = start_pos + 1  # Skip opening brace
            while j < len(text) and depth > 0:
                # Handle escaped braces
                if j + 1 < len(text) and text[j] == '\\' and text[j+1] in ['{', '}']:
                    j += 2
                    continue
                
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                j += 1
            return j
        
        while i < len(text):
            char = text[i]
            
            # Handle backslash
            if char == '\\':
                if i + 1 >= len(text):
                    i += 1
                    continue
                
                next_char = text[i + 1]
                
                # Escaped characters: \\ \{ \}
                if next_char in ['\\', '{', '}']:
                    if not in_skip_group:
                        result.append(next_char)
                    i += 2
                    continue
                
                # Line breaks: \par or \line
                if i + 3 < len(text) and text[i:i+4] == '\\par':
                    if not in_skip_group:
                        result.append('\n')
                    i += 4
                    if i < len(text) and text[i] == ' ':
                        i += 1
                    continue
                elif i + 4 < len(text) and text[i:i+5] == '\\line':
                    if not in_skip_group:
                        result.append('\n')
                    i += 5
                    if i < len(text) and text[i] == ' ':
                        i += 1
                    continue
                elif i + 3 < len(text) and text[i:i+4] == '\\tab':
                    if not in_skip_group:
                        result.append('\t')
                    i += 4
                    if i < len(text) and text[i] == ' ':
                        i += 1
                    continue
                
                # Control word
                if next_char.isalpha():
                    # Read control word
                    j = i + 1
                    while j < len(text) and text[j].isalpha():
                        j += 1
                    while j < len(text) and text[j].isdigit():
                        j += 1
                    if j < len(text) and text[j] == ' ':
                        j += 1
                    i = j
                    continue
                else:
                    # Control symbol - skip
                    i += 2
                    continue
            
            # Handle opening brace
            elif char == '{':
                # Check if this starts a header group we should skip
                if i + 1 < len(text) and text[i + 1] == '\\':
                    # Peek ahead to identify group type
                    k = i + 2
                    while k < len(text) and k < i + 25 and text[k].isalpha():
                        k += 1
                    group_type = text[i+2:k]
                    
                    # Skip header groups entirely
                    if group_type in ('fonttbl', 'colortbl', 'stylesheet', 'info'):
                        i = skip_header_group(i)
                        continue
                
                # Regular brace - skip it but continue extracting text
                i += 1
                continue
            
            # Handle closing brace
            elif char == '}':
                # Skip closing brace
                i += 1
                continue
            
            # Regular character - extract if not in skip group
            else:
                # Extract all regular characters (they're text content)
                result.append(char)
                i += 1
        
        # Join result
        plain_text = ''.join(result)
        
        # Don't remove header keywords - they might be actual text content
        # The parser should have already skipped them properly
        
        # Clean up whitespace
        lines = plain_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Collapse multiple spaces
            line = re.sub(r'  +', ' ', line)
            cleaned_lines.append(line.rstrip())
        plain_text = '\n'.join(cleaned_lines)
        
        # Remove excessive blank lines
        plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)
        
        return plain_text.strip()
    
    def _plain_text_to_rtf(self, plain_text: str) -> str:
        """Convert plain text to RTF format, preserving all formatting for dialogue recognition."""
        # Escape special RTF characters first
        rtf_text = plain_text.replace('\\', '\\\\')
        rtf_text = rtf_text.replace('{', '\\{')
        rtf_text = rtf_text.replace('}', '\\}')
        
        # Preserve all line breaks and whitespace exactly as they are
        # Convert line breaks to RTF paragraph breaks, preserving multiple consecutive breaks
        lines = rtf_text.split('\n')
        rtf_lines = []
        for line in lines:
            # Preserve the line content exactly (including leading/trailing whitespace)
            # Convert tabs to RTF tab command
            line = line.replace('\t', '\\tab ')
            rtf_lines.append(line)
        
        # Join with paragraph breaks, preserving empty lines
        rtf_content = '\\par\n'.join(rtf_lines)
        
        # RTF header with basic formatting (Courier Prime for monospace, matching script format)
        rtf_header = "{\\rtf1\\ansi\\deff0 {\\fonttbl {\\f0 Courier Prime;}}\\f0\\fs24 "
        rtf_footer = "}"
        
        return rtf_header + rtf_content + rtf_footer
    
    def _show_uneditable_message(self, file_path: Path, label_text: str, status_text: str) -> None:
        """Display an informational message for files that cannot be edited."""
        self.current_file_path = file_path
        self.txt_editor.clear()
        self.txt_editor.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.lbl_file.setText(label_text)
        self.lbl_status.setText(status_text)
    
    def show_readonly_info(self, file_path: Path, message: str) -> None:
        """Display a readonly message for files that cannot be edited."""
        self._show_uneditable_message(
            file_path,
            f"Read-only: {file_path.name}",
            message
        )
    
    def show_missing_pdf_message(
        self,
        project_name: str,
        expected_path: Optional[Path] = None,
        project_folder: Optional[Path] = None,
    ) -> None:
        """Display guidance when a project does not yet have an associated PDF."""
        self.current_file_path = None
        self.txt_editor.clear()
        self.txt_editor.setEnabled(False)
        self.btn_save.setEnabled(False)

        self.lbl_file.setText(f"Project: {project_name}")

        message_lines = [
            "No script PDF is currently available for this project.",
            "Use the Files tab to add or convert a script file.",
        ]
        if expected_path:
            message_lines.append(f"Expected PDF location: {expected_path}")
        if project_folder:
            message_lines.append(f"Project folder: {project_folder}")
        message_lines.append("Once a PDF is available, replace the project script to enable parsing.")

        self.lbl_status.setText("\n".join(message_lines))

    def load_file(self, file_path: Path) -> None:
        """Load a file for editing."""
        if not file_path.exists():
            QMessageBox.warning(
                self,
                "File Not Found",
                f"The file does not exist:\n{file_path}"
            )
            return
        
        # Check if this is a PDF - PDFs are not editable within the editor
        if file_path.suffix.lower() == ".pdf":
            self._show_uneditable_message(
                file_path,
                f"PDF: {file_path.name}",
                "PDF files cannot be edited directly within the editor."
            )
            return
        
        # Check if file needs OCR (image without text)
        if not has_text_content(file_path):
            if is_image_file(file_path):
                status = "Image files cannot be edited directly within the editor."
                label = f"Image: {file_path.name}"
            else:
                status = "This file does not contain extractable text and cannot be edited."
                label = f"File: {file_path.name}"
            self._show_uneditable_message(file_path, label, status)
            return
        
        self.txt_editor.setEnabled(True)
        
        # Load file without confirmation dialog
        try:
            # Read file content - RTF files might have different encodings
            # Try UTF-8 first, then fall back to latin-1 (common for RTF)
            content = None
            encoding_used = "utf-8"
            
            if file_path.suffix.lower() == ".rtf":
                # RTF files are typically in Windows-1252 or UTF-8
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    try:
                        content = file_path.read_text(encoding="latin-1", errors="replace")
                        encoding_used = "latin-1"
                    except Exception:
                        # Last resort: read as bytes and decode with errors='replace'
                        content = file_path.read_bytes().decode("utf-8", errors="replace")
            else:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            
            # Handle RTF files - use improved conversion
            if file_path.suffix.lower() == ".rtf":
                content = self._rtf_to_plain_text_improved(content)
            
            self.txt_editor.setPlainText(content)
            self.current_file_path = file_path
            self.is_modified = False
            self.btn_save.setEnabled(False)
            self.lbl_file.setText(f"Editing: {file_path.name}")
            self.lbl_status.setText("File loaded. Make your edits and click 'Save' to save changes.")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading File",
                f"Failed to load file:\n{e}"
            )
    
    def create_new_file(self, folder_path: Path, suggested_name: str = "new_file.txt") -> None:
        """Create a new file in the specified folder."""
        try:
            new_file_path = folder_path / suggested_name
            # If file exists, append a number
            counter = 1
            while new_file_path.exists():
                base = new_file_path.stem
                suffix = new_file_path.suffix
                new_file_path = folder_path / f"{base}_{counter}{suffix}"
                counter += 1
            
            # Create empty file
            new_file_path.write_text("", encoding="utf-8")
            
            # Load it for editing
            self.load_file(new_file_path)
            self.is_modified = True
            self.btn_save.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Creating File",
                f"Failed to create new file:\n{e}"
            )
    
    def _on_save(self) -> None:
        """Save the current file."""
        if not self.current_file_path:
            QMessageBox.warning(
                self,
                "No File",
                "No file is currently open. Please select a file to edit first."
            )
            return
        
        try:
            content = self.txt_editor.toPlainText()
            
            # Convert to RTF format if saving an RTF file
            if self.current_file_path.suffix.lower() == ".rtf":
                content = self._plain_text_to_rtf(content)
            
            self.current_file_path.write_text(content, encoding="utf-8")
            self.is_modified = False
            self.btn_save.setEnabled(False)
            self.lbl_status.setText("File saved successfully!")
            
            # Emit signal to update other tabs (send plain text for parsing)
            plain_text = self.txt_editor.toPlainText()
            self.text_changed.emit(plain_text)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Saving File",
                f"Failed to save file:\n{e}"
            )
    
    def get_current_text(self) -> str:
        """Get the current text content."""
        return self.txt_editor.toPlainText()
    
    def has_unsaved_changes(self) -> bool:
        """Check if there are unsaved changes."""
        return self.is_modified

