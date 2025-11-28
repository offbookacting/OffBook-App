# app/library_creation_dialog.py
"""
Dialog for creating a new library - asks for location and name.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox
)

from core.project_manager import ProjectLibrary


class LibraryCreationDialog(QDialog):
    """Dialog for creating a new library."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.library_path: Optional[Path] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        self.setWindowTitle("Create Library")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Instructions
        instructions = QLabel(
            "Scene Partner needs a library to store your projects.\n\n"
            "Choose where to create the library and what to name it.\n"
            "The library will contain:\n"
            "  • projects/ - folder where project files are stored\n"
            "  • customizations/ - folder for voice presets and user modifications"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Library name
        name_layout = QHBoxLayout()
        name_label = QLabel("Library Name:")
        name_label.setMinimumWidth(120)
        name_layout.addWidget(name_label)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("My Scene Partner Library")
        self.name_input.textChanged.connect(self._validate_inputs)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Library location
        location_layout = QHBoxLayout()
        location_label = QLabel("Location:")
        location_label.setMinimumWidth(120)
        location_layout.addWidget(location_label)
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Choose a folder...")
        self.location_input.setReadOnly(True)
        location_layout.addWidget(self.location_input)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_location)
        location_layout.addWidget(btn_browse)
        layout.addLayout(location_layout)
        
        # Full path preview
        self.path_preview = QLabel("")
        self.path_preview.setWordWrap(True)
        self.path_preview.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.path_preview)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_create = QPushButton("Create Library")
        self.btn_create.setDefault(True)
        self.btn_create.setEnabled(False)
        self.btn_create.clicked.connect(self._create_library)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_create)
        layout.addLayout(btn_layout)
        
        # Set default location
        default_location = Path.home() / "Documents"
        self.location_input.setText(str(default_location))
        self._update_path_preview()
    
    def _browse_location(self) -> None:
        """Browse for library location."""
        current_location = self.location_input.text()
        if not current_location:
            current_location = str(Path.home() / "Documents")
        
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose Library Location",
            current_location
        )
        
        if path:
            self.location_input.setText(path)
            self._update_path_preview()
            self._validate_inputs()
    
    def _update_path_preview(self) -> None:
        """Update the full path preview."""
        location = self.location_input.text().strip()
        name = self.name_input.text().strip()
        
        if location and name:
            full_path = Path(location) / name
            self.path_preview.setText(f"Library will be created at:\n{full_path}")
        else:
            self.path_preview.setText("")
    
    def _validate_inputs(self) -> None:
        """Validate inputs and enable/disable create button."""
        location = self.location_input.text().strip()
        name = self.name_input.text().strip()
        
        # Update path preview
        self._update_path_preview()
        
        # Validate
        if not location or not name:
            self.btn_create.setEnabled(False)
            return
        
        # Check for invalid characters in name
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(char in name for char in invalid_chars):
            self.btn_create.setEnabled(False)
            return
        
        # Check if location exists
        location_path = Path(location)
        if not location_path.exists() or not location_path.is_dir():
            self.btn_create.setEnabled(False)
            return
        
        # Check if library already exists
        full_path = location_path / name
        if full_path.exists():
            self.btn_create.setEnabled(False)
            return
        
        self.btn_create.setEnabled(True)
    
    def _create_library(self) -> None:
        """Create the library."""
        location = Path(self.location_input.text().strip())
        name = self.name_input.text().strip()
        full_path = location / name
        
        # Double-check location exists
        if not location.exists() or not location.is_dir():
            QMessageBox.critical(
                self,
                "Invalid Location",
                f"The selected location does not exist or is not a directory:\n{location}"
            )
            return
        
        # Check if library already exists
        if full_path.exists():
            QMessageBox.warning(
                self,
                "Library Exists",
                f"A folder with that name already exists:\n{full_path}\n\nPlease choose a different name."
            )
            return
        
        try:
            # Create the library folder
            full_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize the library (this will create the required subdirectories)
            ProjectLibrary(str(full_path))
            
            self.library_path = full_path
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create library:\n{e}"
            )

