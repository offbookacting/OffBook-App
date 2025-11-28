# app/tabs/character_color_dialog.py
"""
Color picker dialog for selecting character highlight colors.
"""
from __future__ import annotations
from typing import Optional, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGridLayout, QColorDialog, QLineEdit
)

from app.config import AppConfig

# 20 preset colors that work well with white background and black text
# These are light, pastel colors that maintain readability
PRESET_COLORS = [
    "#FFF59D",  # Soft Yellow (default)
    "#C5E1A5",  # Light Green
    "#A5D6A7",  # Mint Green
    "#90CAF9",  # Light Blue
    "#81D4FA",  # Sky Blue
    "#B39DDB",  # Light Purple
    "#CE93D8",  # Lavender
    "#F48FB1",  # Light Pink
    "#FFAB91",  # Light Coral
    "#FFCC80",  # Light Orange
    "#FFE082",  # Amber
    "#D4E157",  # Lime
    "#AED581",  # Light Green-Yellow
    "#80CBC4",  # Teal
    "#80DEEA",  # Cyan
    "#9FA8DA",  # Indigo
    "#BCAAA4",  # Brown
    "#EF9A9A",  # Light Red
    "#B0BEC5",  # Blue Grey
    "#C8E6C9",  # Very Light Green
]

NO_HIGHLIGHT = "No Highlight"


class CharacterColorDialog(QDialog):
    """Dialog for selecting a character highlight color."""
    
    color_selected = pyqtSignal(str)  # emits color hex string or NO_HIGHLIGHT
    
    def __init__(self, current_color: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.selected_color: Optional[str] = current_color
        self.app_config = AppConfig()
        self.setWindowTitle("Select Character Color")
        self.setModal(True)
        self.resize(450, 400)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Instructions
        label = QLabel("Select a color for character highlighting:")
        layout.addWidget(label)
        
        # Preset colors grid
        grid = QGridLayout()
        grid.setSpacing(5)
        
        # Add "No Highlight" button first
        btn_no_highlight = QPushButton("No Highlight")
        btn_no_highlight.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 2px solid #ccc;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                border-color: #999;
                background-color: #f5f5f5;
            }
        """)
        btn_no_highlight.clicked.connect(lambda: self._select_color(NO_HIGHLIGHT))
        grid.addWidget(btn_no_highlight, 0, 0, 1, 2)
        
        # Add preset color buttons
        row = 1
        col = 0
        for i, color_hex in enumerate(PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(50, 50)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color_hex};
                    border: 2px solid #999;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    border-color: #333;
                    border-width: 3px;
                }}
            """)
            btn.setToolTip(color_hex)
            btn.clicked.connect(lambda checked, c=color_hex: self._select_color(c))
            
            # Highlight current color if it matches
            if self.selected_color and self.selected_color == color_hex:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color_hex};
                        border: 3px solid #000;
                        border-radius: 5px;
                    }}
                    QPushButton:hover {{
                        border-color: #333;
                    }}
                """)
            
            grid.addWidget(btn, row, col)
            col += 1
            if col >= 4:  # 4 columns
                col = 0
                row += 1
        
        layout.addLayout(grid)
        
        # Custom colors section
        custom_label = QLabel("Custom Colors:")
        custom_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(custom_label)
        
        # Custom colors grid
        self.custom_grid = QGridLayout()
        self.custom_grid.setSpacing(5)
        self._update_custom_colors_grid()
        layout.addLayout(self.custom_grid)
        
        # Add custom color section
        add_color_layout = QHBoxLayout()
        add_color_layout.addWidget(QLabel("Add Color:"))
        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText("#RRGGBB")
        self.color_input.setMaximumWidth(100)
        add_color_layout.addWidget(self.color_input)
        
        btn_add = QPushButton("Add to Presets")
        btn_add.clicked.connect(self._add_custom_color)
        add_color_layout.addWidget(btn_add)
        
        btn_custom = QPushButton("Pick Custom...")
        btn_custom.clicked.connect(self._select_custom_color)
        add_color_layout.addWidget(btn_custom)
        
        add_color_layout.addStretch()
        layout.addLayout(add_color_layout)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        buttons.addWidget(btn_ok)
        
        layout.addLayout(buttons)
    
    def _select_color(self, color: str) -> None:
        """Select a color."""
        self.selected_color = color
        self.accept()
    
    def _update_custom_colors_grid(self) -> None:
        """Update the custom colors grid."""
        # Clear existing custom color buttons
        while self.custom_grid.count():
            item = self.custom_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Get custom colors from config
        custom_colors = self.app_config.custom_colors()
        current_color = self.selected_color
        
        if not custom_colors:
            return
        
        # Add custom color buttons
        row = 0
        col = 0
        for color_hex in custom_colors:
            btn = QPushButton()
            btn.setFixedSize(50, 50)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color_hex};
                    border: 2px solid #999;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    border-color: #333;
                    border-width: 3px;
                }}
            """)
            btn.setToolTip(color_hex)
            btn.clicked.connect(lambda checked, c=color_hex: self._select_color(c))
            
            # Highlight current color if it matches
            if current_color and current_color.upper() == color_hex.upper():
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color_hex};
                        border: 3px solid #000;
                        border-radius: 5px;
                    }}
                    QPushButton:hover {{
                        border-color: #333;
                    }}
                """)
            
            self.custom_grid.addWidget(btn, row, col)
            col += 1
            if col >= 4:  # 4 columns
                col = 0
                row += 1
    
    def _add_custom_color(self) -> None:
        """Add a custom color from the input field."""
        color_text = self.color_input.text().strip()
        if not color_text:
            return
        
        # Validate color format
        color = QColor(color_text)
        if not color.isValid():
            # Try with # prefix
            if not color_text.startswith("#"):
                color = QColor("#" + color_text)
            if not color.isValid():
                return
        
        color_hex = color.name().upper()
        
        # Add to config
        self.app_config.add_custom_color(color_hex)
        
        # Update the grid
        self._update_custom_colors_grid()
        
        # Clear input
        self.color_input.clear()
    
    def _select_custom_color(self) -> None:
        """Open system color picker for custom color."""
        if self.selected_color and self.selected_color != NO_HIGHLIGHT:
            initial_color = QColor(self.selected_color)
        else:
            initial_color = QColor("#FFF59D")
        color = QColorDialog.getColor(initial_color, self, "Select Custom Color")
        if color.isValid():
            color_hex = color.name().upper()
            # Add to custom colors if not already in presets or custom colors
            preset_upper = [c.upper() for c in PRESET_COLORS]
            custom_upper = [c.upper() for c in self.app_config.custom_colors()]
            if color_hex not in preset_upper and color_hex not in custom_upper:
                self.app_config.add_custom_color(color_hex)
                self._update_custom_colors_grid()
            self.selected_color = color_hex
            self.accept()
    
    def get_selected_color(self) -> Optional[str]:
        """Get the selected color."""
        return self.selected_color

