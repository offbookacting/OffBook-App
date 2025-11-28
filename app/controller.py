# app/controller.py
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any, Union

from core.project_manager import ProjectManager, ProjectLibraryError, Project
from core.pdf_parser import PDFParser
from core.nlp_processor import (
    parse_script_text,
    list_characters,
    blocks_for_character,
    auto_pick_top_character,
    ScriptParse,
    DialogueBlock,
)

# ----------------------------
# Errors
# ----------------------------

class ControllerError(Exception):
    pass


# ----------------------------
# Value types for GUI consumption
# ----------------------------

@dataclass(frozen=True)
class ScriptView:
    """Thin container the GUI can render."""
    lines: List[str]                      # script as lines (for QTextEdit line mapping)
    characters_ranked: List[str]          # detected characters sorted by frequency
    chosen_character: Optional[str]       # saved character for the project (if any)


# ----------------------------
# Controller
# ----------------------------

class AppController:
    """
    Mediates GUI <-> core modules.
    Holds current project, extracted text, and parsed structure.
    Provides highlighting spans by line index without imposing any widget API.
    """

    def __init__(self, app_name: str = "ActorRehearsal"):
        self.pm = ProjectManager(app_name=app_name)
        self.current_project: Optional[Project] = None
        self.current_text: str = ""
        self.current_parse: Optional[ScriptParse] = None

    # ---------- Library ----------

    def library_path(self) -> Optional[str]:
        return self.pm.config.library_path

    def set_library(self, path: Union[str, Path]) -> None:
        try:
            self.pm.set_library(path)
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e

    # ---------- Projects (CRUD) ----------

    def list_projects(self) -> List[Project]:
        self._require_lib()
        try:
            return self.pm.list()
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e

    def create_project(
        self,
        name: str,
        pdf_path: Union[str, Path],
        copy_into_library: bool = True,
        initial_character: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        open_after_create: bool = True,
    ) -> Project:
        self._require_lib()
        try:
            proj = self.pm.create(
                name=name,
                pdf_path=pdf_path,
                copy_into_library=copy_into_library,
                initial_character=initial_character,
                meta=meta,
            )
            if open_after_create:
                self.open_project(proj.id)
            return proj
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e

    def open_project(self, project_id: int) -> ScriptView:
        self._require_lib()
        try:
            proj = self.pm.get(project_id)
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e
        self.current_project = proj
        self._load_and_parse_pdf(proj.pdf_path)
        chars = list_characters(self.current_parse, sort_by_freq=True) if self.current_parse else []
        return ScriptView(
            lines=(self.current_parse.lines if self.current_parse else self.current_text.splitlines()),
            characters_ranked=chars,
            chosen_character=proj.chosen_character,
        )

    def open_project_by_name(self, name: str) -> ScriptView:
        self._require_lib()
        try:
            proj = self.pm.get_by_name(name)
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e
        return self.open_project(proj.id)

    def rename_project(self, project_id: int, new_name: str) -> Project:
        self._require_lib()
        try:
            proj = self.pm.rename(project_id, new_name)
            if self.current_project and self.current_project.id == project_id:
                self.current_project = proj
            return proj
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e

    def replace_project_pdf(self, project_id: int, new_pdf_path: Union[str, Path], copy_into_library: bool = True) -> ScriptView:
        self._require_lib()
        try:
            proj = self.pm.replace_pdf(project_id, new_pdf_path, copy_into_library=copy_into_library)
            # If it's the current project, reload parse
            if self.current_project and self.current_project.id == project_id:
                self.current_project = proj
                self._load_and_parse_pdf(proj.pdf_path)
            else:
                # Load anyway to return a fresh view
                self.current_project = proj
                self._load_and_parse_pdf(proj.pdf_path)
            chars = list_characters(self.current_parse, sort_by_freq=True) if self.current_parse else []
            return ScriptView(
                lines=(self.current_parse.lines if self.current_parse else self.current_text.splitlines()),
                characters_ranked=chars,
                chosen_character=proj.chosen_character,
            )
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e

    def delete_project(self, project_id: int, remove_file: bool = True) -> None:
        self._require_lib()
        try:
            self.pm.delete(project_id, remove_file=remove_file)
            if self.current_project and self.current_project.id == project_id:
                self.current_project = None
                self.current_text = ""
                self.current_parse = None
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e

    # ---------- Character selection ----------

    def save_chosen_character(self, character: str) -> Project:
        if not self.current_project:
            raise ControllerError("No project is open.")
        try:
            proj = self.pm.set_character(self.current_project.id, character.strip().upper() or None)
            self.current_project = proj
            return proj
        except ProjectLibraryError as e:
            raise ControllerError(str(e)) from e

    def auto_select_top_character(self) -> Optional[str]:
        if not self.current_parse:
            return None
        return auto_pick_top_character(self.current_parse)

    # ---------- Script data / highlighting ----------

    def get_script_view(self) -> ScriptView:
        if not self.current_parse:
            return ScriptView(lines=[], characters_ranked=[], chosen_character=None)
        chars = list_characters(self.current_parse, sort_by_freq=True)
        chosen = self.current_project.chosen_character if self.current_project else None
        return ScriptView(lines=self.current_parse.lines, characters_ranked=chars, chosen_character=chosen)

    def get_highlight_spans_for_character(self, character: str) -> List[Tuple[int, int]]:
        """
        Returns list of (start_line, end_line) inclusive spans for the character’s dialogue blocks.
        GUI can convert these to text ranges using its own line->offset mapping.
        """
        if not self.current_parse:
            return []
        spans: List[Tuple[int, int]] = []
        for b in blocks_for_character(self.current_parse, character):
            spans.append((max(0, b.start_line), max(b.start_line, b.end_line)))
        return spans

    def get_blocks_for_character(self, character: str) -> List[DialogueBlock]:
        if not self.current_parse:
            return []
        return blocks_for_character(self.current_parse, character)

    # ---------- Internals ----------

    def _load_and_parse_pdf(self, pdf_path: Union[str, Path]) -> None:
        pdf_path = str(Path(pdf_path).expanduser())
        try:
            parser = PDFParser(pdf_path)
            self.current_text = parser.extract_text(preserve_layout=True, ocr_if_empty=True)
            parser.close()
        except Exception as e:
            raise ControllerError(f"Failed to parse PDF: {e}") from e
        self.current_parse = parse_script_text(self.current_text)

    def _require_lib(self) -> None:
        if not self.pm.library:
            raise ControllerError("No library set. Call set_library(<folder>) first.")