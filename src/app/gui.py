# app/gui.py
from __future__ import annotations
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QTextCharFormat, QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QComboBox, QTextEdit, QSplitter, QToolBar, QStatusBar
)

# Core modules
from core.project_manager import ProjectManager, ProjectLibraryError, Project
from core.pdf_parser import PDFParser
from core.nlp_processor import parse_script_text, list_characters, blocks_for_character, ScriptParse


# ----------------------------
# Utility
# ----------------------------

def _err(parent: QWidget, msg: str) -> None:
    _ = QMessageBox.critical(parent, "Error", msg)

def _info(parent: QWidget, msg: str) -> None:
    _= QMessageBox.information(parent, "Info", msg)

def _confirm(parent: QWidget, msg: str) -> bool:
    return QMessageBox.question(parent, "Confirm", msg) == QMessageBox.StandardButton.Yes


# ----------------------------
# Main Window
# ----------------------------

class MainWindow(QMainWindow):
    """
    macOS-friendly PyQt6 GUI:
      - Library chooser (user-selected folder acts as “database”)
      - Project list (create/open/delete/rename)
      - Script view with character selector and highlight of chosen character’s lines
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Actor Rehearsal")
        self.resize(1200, 800)
        self.pm = ProjectManager(app_name="ActorRehearsal")

        # State
        self.current_project: Project | None = None
        self.current_text: str = ""
        self.current_parse: ScriptParse | None = None
        self.line_offsets: list[int] = []  # cumulative char offsets for each line

        # UI
        self._build_actions()
        self._build_toolbar()
        self._build_content()
        self.setStatusBar(QStatusBar(self))

        # Initial load
        statusbar = self.statusBar()
        if isinstance(statusbar, QStatusBar):
            if self.pm.config.library_path:
                statusbar.showMessage(f"Library: {self.pm.config.library_path}")
                self._refresh_project_list()
            else:
                statusbar.showMessage("No library set. Choose Library to begin.")

    # ---- UI builders ----

    def _build_actions(self) -> None:
        self.act_choose_library= QAction("Choose Library…", self)
        self.act_choose_library.triggered.connect(self.on_choose_library)

        self.act_new_project = QAction("New Project…", self)
        self.act_new_project.triggered.connect(self.on_new_project)

        self.act_open_project = QAction("Open Project", self)
        self.act_open_project.triggered.connect(self.on_open_selected)

        self.act_delete_project = QAction("Delete Project", self)
        self.act_delete_project.triggered.connect(self.on_delete_selected)

        self.act_rename_project = QAction("Rename Project…", self)
        self.act_rename_project.triggered.connect(self.on_rename_selected)

        self.act_reimport_pdf = QAction("Replace Script PDF…", self)
        self.act_reimport_pdf.triggered.connect(self.on_replace_pdf)

        self.act_quit = QAction("Quit", self)
        self.act_quit.triggered.connect(self.close)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setIconSize(QSize(18, 18))
        tb.addAction(self.act_choose_library)
        tb.addSeparator()
        tb.addAction(self.act_new_project)
        tb.addAction(self.act_open_project)
        tb.addAction(self.act_delete_project)
        tb.addAction(self.act_rename_project)
        tb.addSeparator()
        tb.addAction(self.act_reimport_pdf)
        tb.addSeparator()
        tb.addAction(self.act_quit)
        self.addToolBar(tb)

    def _build_content(self) -> None:
        # Left: project list
        self.list_projects = QListWidget()
        self.list_projects.itemDoubleClicked.connect(lambda _: self.on_open_selected())

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("Projects"))
        left_box.addWidget(self.list_projects)
        left_panel = QWidget()
        left_panel.setLayout(left_box)

        # Right: script area
        self.lbl_project = QLabel("No project open")
        self.cmb_char = QComboBox()
        self.cmb_char.currentTextChanged.connect(self.on_character_changed)
        self.btn_select_char = QPushButton("Use Selected Character")
        self.btn_select_char.clicked.connect(self.on_set_project_character)

        header = QHBoxLayout()
        header.addWidget(self.lbl_project, stretch=1)
        header.addWidget(QLabel("Character:"))
        header.addWidget(self.cmb_char)
        header.addWidget(self.btn_select_char)

        self.txt_script = QTextEdit()
        self.txt_script.setReadOnly(True)
        self.txt_script.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        # macOS font readability
        self.txt_script.setFontFamily("Menlo")
        self.txt_script.setFontPointSize(12)

        right_box = QVBoxLayout()
        right_box.addLayout(header)
        right_box.addWidget(self.txt_script, stretch=1)
        right_panel = QWidget()
        right_panel.setLayout(right_box)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 1)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    # ---- Data/UI sync ----

    def _refresh_project_list(self) -> None:
        self.list_projects.clear()
        try:
            for proj in self.pm.list():
                item = QListWidgetItem(proj.name)
                item.setData(Qt.ItemDataRole.UserRole, proj.id)
                self.list_projects.addItem(item)
        except ProjectLibraryError as e:
            _err(self, str(e))

    def _current_selected_project_id(self) -> int | None:
        item = self.list_projects.currentItem()
        if not item:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _load_project(self, proj: Project) -> None:
        self.current_project = proj
        self.lbl_project.setText(f"Project: {proj.name}  |  PDF: {proj.pdf_path}")
        # Extract text
        try:
            parser = PDFParser(proj.pdf_path)
            full_text = parser.extract_text(preserve_layout=True, ocr_if_empty=True)
            parser.close()
        except Exception as e:
            _err(self, f"Failed to read PDF:\n{e}")
            return
        self.current_text = full_text if full_text else ""
        # Parse
        self.current_parse = parse_script_text(self.current_text)
        self._populate_character_combo(proj)
        # Show text and apply highlight (if a character is already chosen)
        self._set_script_text(self.current_parse.lines if self.current_parse else self.current_text.splitlines())
        if proj.chosen_character:
            self._highlight_character(proj.chosen_character)

    def _populate_character_combo(self, proj: Project) -> None:
        self.cmb_char.blockSignals(True)
        self.cmb_char.clear()
        if not self.current_parse:
            self.cmb_char.blockSignals(False)
            return
        chars = list_characters(self.current_parse, sort_by_freq=True)
        self.cmb_char.addItems(chars)
        # Preselect project’s chosen character if present
        if proj.chosen_character and proj.chosen_character in chars:
            self.cmb_char.setCurrentText(proj.chosen_character)
        self.cmb_char.blockSignals(False)

    def _set_script_text(self, lines: list[str]) -> None:
        # Build offsets per line for highlighting by line-span
        self.line_offsets = []
        buf = []
        offset = 0
        for i, ln in enumerate(lines):
            self.line_offsets.append(offset)
            buf.append(ln)
            offset += len(ln) + 1  # +1 for newline we insert
        text = "\n".join(buf)
        self.txt_script.clear()
        self.txt_script.setPlainText(text)

    def _highlight_character(self, character: str) -> None:
        if not self.current_parse:
            return
        # Clear formats
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        cursor.select(cursor.SelectionType.Document)
        default_fmt = QTextCharFormat()
        self.txt_script.textCursor().mergeCharFormat(default_fmt)
        cursor.endEditBlock()

        # Prepare highlight format
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FFF59D"))  # soft yellow
        fmt.setFontWeight(600)

        blocks = blocks_for_character(self.current_parse, character)
        statusbar = self.statusBar()
        if isinstance(statusbar, QStatusBar):
            if not blocks:
                statusbar.showMessage(f"No blocks found for {character}", 5000)
                return

        doc = self.txt_script.document()
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        for b in blocks:
            start_line = max(0, b.start_line)
            end_line = max(start_line, b.end_line)
            if start_line >= len(self.line_offsets):
                continue
            start_pos = self.line_offsets[start_line]
            # inclusive end_line
            end_pos = self.line_offsets[end_line] + len(self.current_parse.lines[end_line]) if end_line < len(self.line_offsets) else len(self.txt_script.toPlainText())
            # Apply format
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, cursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)
        cursor.endEditBlock()
        statusbar = self.statusBar()
        if isinstance(statusbar, QStatusBar):
            statusbar.showMessage(f"Highlighted lines for {character}", 3000)

    # ---- Slots ----

    def on_choose_library(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Project Library Folder")
        if not path:
            return
        try:
            self.pm.set_library(path)
            statusbar = self.statusBar()
            if isinstance(statusbar, QStatusBar):
                statusbar.showMessage(f"Library: {path}")
            self._refresh_project_list()
        except ProjectLibraryError as e:
            _err(self, str(e))

    def on_new_project(self) -> None:
        if not self.pm.config.library_path:
            _err(self, "Set a library folder first.")
            return
        pdf_path, _ = QFileDialog.getOpenFileName(self, "Choose Script PDF", "", "PDF Files (*.pdf)")
        if not pdf_path:
            return
        base = Path(pdf_path).stem
        name, ok = QFileDialog.getSaveFileName(self, "Name Your Project (save to suggest name only)", base, "")
        # If user cancels name dialog, use default base name (without writing file)
        project_name = Path(name).name if ok and name else base
        try:
            proj = self.pm.create(project_name, pdf_path, copy_into_library=True, initial_character=None)
        except ProjectLibraryError as e:
            _err(self, str(e))
            return
        self._refresh_project_list()
        # Select and open it
        for i in range(self.list_projects.count()):
            item = self.list_projects.item(i)
            if isinstance(item, QListWidgetItem):
                if item.text() == proj.name:
                    self.list_projects.setCurrentRow(i)
                    break
        self._load_project(proj)

    def on_open_selected(self) -> None:
        pid = self._current_selected_project_id()
        if pid is None:
            _err(self, "Select a project first.")
            return
        try:
            proj = self.pm.get(pid)
        except ProjectLibraryError as e:
            _err(self, str(e))
            return
        self._load_project(proj)

    def on_delete_selected(self) -> None:
        pid = self._current_selected_project_id()
        if pid is None:
            _err(self, "Select a project first.")
            return
        if not _confirm(self, "Delete this project from the library? This cannot be undone."):
            return
        try:
            self.pm.delete(pid, remove_folder=True)
            self.current_project = None
            self.current_parse = None
            self.txt_script.clear()
            self.cmb_char.clear()
            self.lbl_project.setText("No project open")
            self._refresh_project_list()
        except ProjectLibraryError as e:
            _err(self, str(e))

    def on_rename_selected(self) -> None:
        pid = self._current_selected_project_id()
        if pid is None:
            _err(self, "Select a project first.")
            return
        new_name, _ = QFileDialog.getSaveFileName(self, "New Project Name (save to suggest name only)", "", "")
        if not new_name:
            return
        try:
            proj = self.pm.rename(pid, Path(new_name).name)
            self._refresh_project_list()
            statusbar = self.statusBar()
            if isinstance(statusbar, QStatusBar):
                statusbar.showMessage(f"Renamed to {proj.name}", 3000)
        except ProjectLibraryError as e:
            _err(self, str(e))

    def on_replace_pdf(self) -> None:
        if not self.current_project:
            _err(self, "Open a project first.")
            return
        pdf_path, _ = QFileDialog.getOpenFileName(self, "Replace Script PDF", "", "PDF Files (*.pdf)")
        if not pdf_path:
            return
        try:
            proj = self.pm.replace_pdf(self.current_project.id, pdf_path, copy_into_library=True)
            self._load_project(proj)
            statusbar = self.statusBar()
            if isinstance(statusbar, QStatusBar):
                statusbar.showMessage("Script PDF replaced.", 3000)
        except ProjectLibraryError as e:
            _err(self, str(e))

    def on_character_changed(self, name: str) -> None:
        if not name:
            return
        # Preview highlight without saving
        self._highlight_character(name)

    def on_set_project_character(self) -> None:
        if not self.current_project:
            _err(self, "Open a project first.")
            return
        name = self.cmb_char.currentText().strip()
        if not name:
            _err(self, "Select a character.")
            return
        try:
            proj = self.pm.set_character(self.current_project.id, name)
            self.current_project = proj
            self._highlight_character(name)
            statusbar = self.statusBar()
            if isinstance(statusbar, QStatusBar):
                statusbar.showMessage(f"Character saved: {name}", 3000)
        except ProjectLibraryError as e:
            _err(self, str(e))


# ----------------------------
# Entry point
# ----------------------------

def run() -> None:
    app = QApplication(sys.argv)
    # Optional: load stylesheet if present
    qss_path = Path(__file__).resolve().parent.parent / "ui" / "styles.qss"
    if qss_path.exists():
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    win = MainWindow()
    # Optional icons (if provided)
    icons_dir = Path(__file__).resolve().parent.parent / "ui" / "icons"
    if icons_dir.exists():
        win.setWindowIcon(QIcon(str(icons_dir / "open_project.png")) if (icons_dir / "open_project.png").exists() else QIcon())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()