# app/settings_dialog.py
"""
Settings dialog for application preferences.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QComboBox, QCheckBox, QGroupBox, QFormLayout, QScrollArea, QWidget,
    QColorDialog, QLineEdit, QFileDialog, QMessageBox, QDialogButtonBox
)

from app.config import AppConfig


class SettingsDialog(QDialog):
    """Dialog for application settings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_config = AppConfig()
        self.setWindowTitle("Settings")
        self.resize(700, 600)
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        
        # Scroll area for settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15)
        
        # Editor Settings
        editor_group = QGroupBox("Editor Settings")
        editor_layout = QFormLayout()
        
        self.font_family_combo = QComboBox()
        self.font_family_combo.setEditable(True)
        # Add common monospace fonts
        common_fonts = [
            "Courier Prime", "Courier New", "Monaco", "Menlo", "Consolas",
            "Source Code Pro", "Fira Code", "JetBrains Mono", "Inconsolata"
        ]
        self.font_family_combo.addItems(common_fonts)
        editor_layout.addRow("Font Family:", self.font_family_combo)
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 72)
        self.font_size_spin.setValue(12)
        editor_layout.addRow("Font Size:", self.font_size_spin)
        
        self.word_wrap_check = QCheckBox("Enable word wrap")
        editor_layout.addRow("", self.word_wrap_check)
        
        editor_group.setLayout(editor_layout)
        scroll_layout.addWidget(editor_group)
        
        # Highlight Settings
        highlight_group = QGroupBox("Highlight Settings")
        highlight_layout = QFormLayout()
        
        self.highlight_color_btn = QPushButton()
        self.highlight_color_btn.setFixedSize(60, 30)
        self.highlight_color_btn.clicked.connect(self._choose_highlight_color)
        highlight_layout.addRow("Highlight Color:", self.highlight_color_btn)
        
        self.highlight_weight_spin = QSpinBox()
        self.highlight_weight_spin.setRange(100, 900)
        self.highlight_weight_spin.setSingleStep(100)
        self.highlight_weight_spin.setValue(600)
        highlight_layout.addRow("Font Weight:", self.highlight_weight_spin)
        
        highlight_group.setLayout(highlight_layout)
        scroll_layout.addWidget(highlight_group)
        
        # Rehearse Highlighting Options
        rehearse_highlight_group = QGroupBox("Rehearse Highlighting Options")
        rehearse_highlight_layout = QVBoxLayout()
        
        self.enable_highlighting_check = QCheckBox("Enable highlighting")
        rehearse_highlight_layout.addWidget(self.enable_highlighting_check)
        
        self.highlight_character_names_check = QCheckBox("Highlight character names")
        rehearse_highlight_layout.addWidget(self.highlight_character_names_check)
        
        self.highlight_parentheticals_check = QCheckBox("Highlight parentheticals")
        rehearse_highlight_layout.addWidget(self.highlight_parentheticals_check)
        
        self.smoosh_hieroglyphs_check = QCheckBox("Smoosh hieroglyphs")
        rehearse_highlight_layout.addWidget(self.smoosh_hieroglyphs_check)
        
        rehearse_highlight_group.setLayout(rehearse_highlight_layout)
        scroll_layout.addWidget(rehearse_highlight_group)
        
        # Rehearse Alignment Options
        rehearse_alignment_group = QGroupBox("Rehearse Alignment Options")
        rehearse_alignment_layout = QFormLayout()
        
        self.character_names_alignment = QComboBox()
        self.character_names_alignment.addItems(["left", "center", "right"])
        rehearse_alignment_layout.addRow("Character Names:", self.character_names_alignment)
        
        self.dialogue_alignment = QComboBox()
        self.dialogue_alignment.addItems(["left", "center", "right"])
        rehearse_alignment_layout.addRow("Dialogue:", self.dialogue_alignment)
        
        self.narrator_alignment = QComboBox()
        self.narrator_alignment.addItems(["left", "center", "right"])
        rehearse_alignment_layout.addRow("Narrator:", self.narrator_alignment)
        
        self.everything_else_alignment = QComboBox()
        self.everything_else_alignment.addItems(["left", "center", "right"])
        rehearse_alignment_layout.addRow("Everything Else:", self.everything_else_alignment)
        
        rehearse_alignment_group.setLayout(rehearse_alignment_layout)
        scroll_layout.addWidget(rehearse_alignment_group)
        
        # TTS Settings
        tts_group = QGroupBox("Text-to-Speech Settings")
        tts_layout = QFormLayout()
        
        model_layout = QHBoxLayout()
        self.tts_model_path_edit = QLineEdit()
        self.tts_model_path_edit.setReadOnly(True)
        model_browse_btn = QPushButton("Browse...")
        model_browse_btn.clicked.connect(self._browse_tts_model)
        model_clear_btn = QPushButton("Clear")
        model_clear_btn.clicked.connect(self._clear_tts_model)
        model_layout.addWidget(self.tts_model_path_edit)
        model_layout.addWidget(model_browse_btn)
        model_layout.addWidget(model_clear_btn)
        model_widget = QWidget()
        model_widget.setLayout(model_layout)
        tts_layout.addRow("Model Path:", model_widget)
        
        self.tts_speaker_spin = QSpinBox()
        self.tts_speaker_spin.setRange(0, 100)
        self.tts_speaker_spin.setSpecialValueText("Default")
        tts_layout.addRow("Speaker ID:", self.tts_speaker_spin)
        
        tts_group.setLayout(tts_layout)
        scroll_layout.addWidget(tts_group)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._apply_and_close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_settings)
        layout.addWidget(buttons)
    
    def _load_settings(self) -> None:
        """Load current settings from config."""
        # Editor settings
        editor_prefs = self.app_config.editor_prefs()
        font_family = editor_prefs.get("font_family", "Courier Prime")
        index = self.font_family_combo.findText(font_family)
        if index >= 0:
            self.font_family_combo.setCurrentIndex(index)
        else:
            self.font_family_combo.setCurrentText(font_family)
        self.font_size_spin.setValue(editor_prefs.get("font_size", 12))
        self.word_wrap_check.setChecked(editor_prefs.get("wrap", False))
        
        # Highlight settings
        highlight_style = self.app_config.highlight_style()
        color = highlight_style.get("color", "#FFF59D")
        self._update_color_button(color)
        self.highlight_weight_spin.setValue(highlight_style.get("weight", 600))
        
        # Rehearse highlighting options
        highlighting_options = self.app_config.rehearse_highlighting_options()
        self.enable_highlighting_check.setChecked(highlighting_options.get("enable_highlighting", True))
        self.highlight_character_names_check.setChecked(highlighting_options.get("highlight_character_names", False))
        self.highlight_parentheticals_check.setChecked(highlighting_options.get("highlight_parentheticals", False))
        self.smoosh_hieroglyphs_check.setChecked(highlighting_options.get("smoosh_hieroglyphs", False))
        
        # Rehearse alignment options
        alignment_options = self.app_config.rehearse_alignment_options()
        self.character_names_alignment.setCurrentText(alignment_options.get("character_names", "center"))
        self.dialogue_alignment.setCurrentText(alignment_options.get("dialogue", "center"))
        self.narrator_alignment.setCurrentText(alignment_options.get("narrator", "left"))
        self.everything_else_alignment.setCurrentText(alignment_options.get("everything_else", "left"))
        
        # TTS settings
        tts_config = self.app_config.tts_config()
        model_path = self.app_config.tts_model_path()
        if model_path:
            self.tts_model_path_edit.setText(model_path)
        else:
            self.tts_model_path_edit.setText("")
        speaker = self.app_config.tts_speaker()
        if speaker is not None:
            self.tts_speaker_spin.setValue(speaker)
        else:
            self.tts_speaker_spin.setValue(0)
    
    def _update_color_button(self, color_hex: str) -> None:
        """Update the color button to show the selected color."""
        color = QColor(color_hex)
        style = f"background-color: {color_hex}; border: 1px solid #ccc; border-radius: 3px;"
        self.highlight_color_btn.setStyleSheet(style)
        self.highlight_color_btn.setProperty("color", color_hex)
    
    def _choose_highlight_color(self) -> None:
        """Open color picker for highlight color."""
        current_color = self.highlight_color_btn.property("color") or "#FFF59D"
        color = QColorDialog.getColor(QColor(current_color), self, "Choose Highlight Color")
        if color.isValid():
            color_hex = color.name()
            self._update_color_button(color_hex)
    
    def _browse_tts_model(self) -> None:
        """Browse for TTS model file."""
        start_dir = ""
        if self.tts_model_path_edit.text():
            model_path = Path(self.tts_model_path_edit.text())
            if model_path.exists():
                start_dir = str(model_path.parent)
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TTS Model",
            start_dir,
            "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)"
        )
        if path:
            try:
                self.app_config.set_tts_model_path(path)
                self.tts_model_path_edit.setText(path)
            except ValueError as e:
                QMessageBox.warning(self, "Invalid Model Path", str(e))
    
    def _clear_tts_model(self) -> None:
        """Clear TTS model path."""
        # Directly modify config to clear the path
        self.app_config._data.setdefault("tts", {})
        self.app_config._data["tts"]["model_path"] = ""
        self.app_config._save()
        self.tts_model_path_edit.setText("")
    
    def _apply_settings(self) -> None:
        """Apply settings to config."""
        # Editor settings
        self.app_config.set_editor_prefs(
            font_family=self.font_family_combo.currentText(),
            font_size=self.font_size_spin.value(),
            wrap=self.word_wrap_check.isChecked()
        )
        
        # Highlight settings
        color = self.highlight_color_btn.property("color") or "#FFF59D"
        self.app_config.set_highlight_style(
            color=color,
            weight=self.highlight_weight_spin.value()
        )
        
        # Rehearse highlighting options
        self.app_config.set_rehearse_highlighting_option("enable_highlighting", self.enable_highlighting_check.isChecked())
        self.app_config.set_rehearse_highlighting_option("highlight_character_names", self.highlight_character_names_check.isChecked())
        self.app_config.set_rehearse_highlighting_option("highlight_parentheticals", self.highlight_parentheticals_check.isChecked())
        self.app_config.set_rehearse_highlighting_option("smoosh_hieroglyphs", self.smoosh_hieroglyphs_check.isChecked())
        
        # Rehearse alignment options
        self.app_config.set_rehearse_alignment_option("character_names", self.character_names_alignment.currentText())
        self.app_config.set_rehearse_alignment_option("dialogue", self.dialogue_alignment.currentText())
        self.app_config.set_rehearse_alignment_option("narrator", self.narrator_alignment.currentText())
        self.app_config.set_rehearse_alignment_option("everything_else", self.everything_else_alignment.currentText())
        
        # TTS settings
        if self.tts_model_path_edit.text():
            try:
                self.app_config.set_tts_model_path(self.tts_model_path_edit.text())
            except ValueError as e:
                QMessageBox.warning(self, "Invalid Model Path", str(e))
                return
        
        speaker_value = self.tts_speaker_spin.value()
        self.app_config.set_tts_speaker(speaker_value if speaker_value > 0 else None)
        
        QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
    
    def _apply_and_close(self) -> None:
        """Apply settings and close dialog."""
        self._apply_settings()
        self.accept()

