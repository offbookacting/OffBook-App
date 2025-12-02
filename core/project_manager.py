# core/project_manager.py
from __future__ import annotations
import os
import sqlite3
import json
import shutil
import time
import sys
import platform
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterable, Tuple, Union, Callable, Set

# ----------------------------
# Data models
# ----------------------------

@dataclass
class Project:
    id: int
    name: str
    pdf_path: str                 # absolute path to the script PDF
    chosen_character: Optional[str]
    created_at: float             # epoch seconds
    updated_at: float             # epoch seconds
    meta: Dict[str, Any]          # arbitrary JSON (e.g., cached parse hints)

# ----------------------------
# Paths and Config
# ----------------------------

def mac_app_support_dir(app_name: str = "ActorRehearsal") -> Path:
    """
    Get the application support directory for the current platform.
    - macOS: ~/Library/Application Support/<app_name>
    - Windows: %APPDATA%/<app_name>
    - Linux: ~/.config/<app_name>
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        base = Path.home() / "Library" / "Application Support" / app_name
    elif system == "Windows":  # Windows
        appdata = os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")
        base = Path(appdata) / app_name
    else:  # Linux and other Unix-like systems
        base = Path.home() / ".config" / app_name
    
    base.mkdir(parents=True, exist_ok=True)
    return base

class Config:
    """Stores app-level settings (e.g., last library path)."""
    def __init__(self, app_name: str = "ActorRehearsal"):
        self._app_dir = mac_app_support_dir(app_name)
        self._config_path = self._app_dir / "config.json"
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._config_path.exists():
            try:
                self._data = json.loads(self._config_path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        self._config_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    @property
    def library_path(self) -> Optional[str]:
        return self._data.get("library_path")

    @library_path.setter
    def library_path(self, p: Optional[str]) -> None:
        if p is None:
            self._data.pop("library_path", None)
        else:
            self._data["library_path"] = str(p)
        self.save()

# ----------------------------
# Project Library (folder = “database”)
# ----------------------------

class ProjectLibraryError(Exception):
    pass

class ProjectLibrary:
    """
    A library is a user-selected folder. Inside it we keep:
      <LIBRARY_ROOT>/
        projects/                # folder containing project files (any file = a project)
          file1.pdf              # project file
          file2.pdf              # project file
        customizations/          # user modifications (voice presets, etc.)
          voice_presets/         # voice presets shared across all projects
        .rehearsal/              # app settings and database
          projects.db
          attachments/           # optional future assets per project
    """
    DB_SUBDIR = ".rehearsal"
    DB_FILE = "projects.db"
    ATTACH_DIR = "attachments"
    CUSTOMIZATIONS_DIR = "customizations"
    VOICE_PRESETS_DIR = "voice_presets"
    RESOURCES_DIR = "resources"
    PROJECTS_DIR = "projects"

    @staticmethod
    def resolve_library_root(selected_path: Union[str, Path]) -> Path:
        """
        Given a user-selected directory, resolve the actual library root.
        This handles cases where the user selects a subfolder (e.g., a project
        inside <library>/projects/) or the projects folder itself.
        """
        path = Path(selected_path).expanduser().resolve()
        candidates = [path] + list(path.parents)

        # Prefer a directory that already contains the app metadata (.rehearsal)
        for candidate in candidates:
            if (candidate / ProjectLibrary.DB_SUBDIR).exists():
                return candidate

        # If the selection is within the projects directory, step back to its parent
        for candidate in candidates:
            if candidate.name == ProjectLibrary.PROJECTS_DIR and candidate.parent.exists():
                return candidate.parent

        # If any ancestor already contains a projects folder, use that ancestor
        for candidate in candidates:
            if (candidate / ProjectLibrary.PROJECTS_DIR).exists():
                return candidate

        # As a fallback, return the resolved selection itself
        return path

    def __init__(self, root: Union[str, Path]):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise ProjectLibraryError(f"Library folder does not exist: {self.root}")
        if not self.root.is_dir():
            raise ProjectLibraryError(f"Not a directory: {self.root}")
        # Create projects folder for storing project files (any file = a project)
        self._projects_dir = self.root / self.PROJECTS_DIR
        self._projects_dir.mkdir(parents=True, exist_ok=True)
        # Create customizations folder for user modifications
        self._customizations_dir = self.root / self.CUSTOMIZATIONS_DIR
        self._customizations_dir.mkdir(parents=True, exist_ok=True)
        # Create voice_presets folder inside customizations
        self._voice_presets_dir = self._customizations_dir / self.VOICE_PRESETS_DIR
        self._voice_presets_dir.mkdir(parents=True, exist_ok=True)
        
        # Create models directory for voice files
        self._models_dir = self._customizations_dir / "models"
        self._models_dir.mkdir(parents=True, exist_ok=True)
        
        # Create resources folder for shared web links and resources
        self._resources_dir = self._customizations_dir / self.RESOURCES_DIR
        self._resources_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if voices need to be installed (only if library is new and no voices exist)
        self._check_and_install_voices()
        
        # Create .rehearsal folder for app settings and database
        self._db_dir = self.root / self.DB_SUBDIR
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._attach_dir = self._db_dir / self.ATTACH_DIR
        self._attach_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._db_dir / self.DB_FILE
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()
        self._normalize_existing_projects()

    # ---------- DB core ----------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _ensure_db(self) -> None:
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                pdf_path TEXT NOT NULL,
                chosen_character TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                meta_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)")
        conn.commit()

    def _now(self) -> float:
        return time.time()
    
    def _check_and_install_voices(self) -> None:
        """Check if voices need to be installed and mark for installation."""
        from core.voice_installer import VoiceInstaller
        
        # Check if voices already exist
        if VoiceInstaller.has_voices(self._voice_presets_dir):
            return
        
        # Mark that voices need to be installed (we'll do it in the UI thread)
        # Store a flag that the UI can check
        self._voices_need_installation = True
        self._models_dir = self._customizations_dir / "models"

    def _normalize_existing_projects(self) -> None:
        """
        Ensure all stored project paths live under <library>/projects/<project_name>.
        If older data placed project folders/files outside that directory, move them
        back into place and update the database metadata.
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, name, pdf_path, meta_json FROM projects"
        ).fetchall()

        for row in rows:
            project_id = row["id"]
            name = row["name"]
            raw_pdf_path = row["pdf_path"]
            meta: Dict[str, Any] = {}
            if row["meta_json"]:
                try:
                    meta = json.loads(row["meta_json"])
                except Exception:
                    meta = {}

            expected_folder = (self._projects_dir / name).resolve()
            pdf_path = Path(raw_pdf_path).expanduser() if raw_pdf_path else None
            updated_path: Optional[Path] = None
            updated_meta = dict(meta)

            def ensure_expected_folder() -> None:
                expected_folder.mkdir(parents=True, exist_ok=True)

            def move_folder_contents(src: Path, dest: Path) -> None:
                dest.mkdir(parents=True, exist_ok=True)
                for child in src.iterdir():
                    target = dest / child.name
                    if target.exists():
                        # Skip collision to avoid overwriting unexpectedly.
                        continue
                    shutil.move(str(child), str(target))
                try:
                    src.rmdir()
                except OSError:
                    pass

            if pdf_path:
                pdf_path = pdf_path.resolve()
                if expected_folder in pdf_path.parents:
                    # Already in the correct location.
                    updated_meta["folder_path"] = str(expected_folder)
                    continue

                current_parent = pdf_path.parent
                ensure_expected_folder()

                if (
                    current_parent.exists()
                    and current_parent.is_dir()
                    and current_parent.name == name
                    and current_parent.parent.resolve() == self.root
                ):
                    # Entire project folder is sitting alongside projects/. Move it back.
                    move_folder_contents(current_parent, expected_folder)
                    updated_path = (expected_folder / pdf_path.name).resolve()
                elif pdf_path.exists():
                    # Move the file itself into the expected folder.
                    dest = expected_folder / pdf_path.name
                    counter = 1
                    base = dest.stem
                    suffix = dest.suffix
                    while dest.exists() and dest != pdf_path:
                        dest = expected_folder / f"{base}_{counter}{suffix}"
                        counter += 1
                    shutil.move(str(pdf_path), str(dest))
                    updated_path = dest.resolve()
                else:
                    # File missing; just repoint to expected folder.
                    filename = pdf_path.name if pdf_path.name else "script.pdf"
                    updated_path = (expected_folder / filename).resolve()
            else:
                ensure_expected_folder()
                updated_path = (expected_folder / "script.pdf").resolve()

            updated_meta["folder_path"] = str(expected_folder)

            if updated_path and str(updated_path) != raw_pdf_path:
                conn.execute(
                    "UPDATE projects SET pdf_path = ?, meta_json = ?, updated_at = ? WHERE id = ?",
                    (
                        str(updated_path),
                        json.dumps(updated_meta, ensure_ascii=False),
                        self._now(),
                        project_id,
                    ),
                )
                conn.commit()
            elif updated_meta != meta:
                conn.execute(
                    "UPDATE projects SET meta_json = ? WHERE id = ?",
                    (json.dumps(updated_meta, ensure_ascii=False), project_id),
                )
                conn.commit()
    
    def needs_voice_installation(self) -> bool:
        """Check if voices need to be installed."""
        return getattr(self, '_voices_need_installation', False)
    
    def get_voice_directories(self) -> tuple[Path, Path]:
        """Get models and presets directories for voice installation."""
        models_dir = self._customizations_dir / "models"
        return models_dir, self._voice_presets_dir

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        meta = {}
        if row["meta_json"]:
            try:
                meta = json.loads(row["meta_json"])
            except Exception:
                meta = {}
        return Project(
            id=row["id"],
            name=row["name"],
            pdf_path=row["pdf_path"],
            chosen_character=row["chosen_character"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            meta=meta,
        )

    # ---------- CRUD ----------

    def create_project(
        self,
        name: str,
        pdf_source_path: Union[str, Path],
        copy_into_library: bool = True,
        project_subdir: Optional[str] = None,  # Deprecated, kept for compatibility
        initial_character: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Project:
        """
        Register a new project. Copies the PDF into <library>/projects/<filename>.
        If copy_into_library is False and PDF doesn't exist, creates a placeholder entry.
        """
        name = name.strip()
        if not name:
            raise ProjectLibraryError("Project name is required.")
        pdf_source = Path(pdf_source_path).expanduser().resolve()
        
        # Allow placeholder PDFs (for files without PDFs yet)
        if not pdf_source.exists() and copy_into_library:
            raise ProjectLibraryError(f"PDF not found: {pdf_source}")

        # Copy file directly into projects folder
        if copy_into_library and pdf_source.exists():
            # Use project name as filename, preserving the source file extension
            source_ext = pdf_source.suffix if pdf_source.suffix else ".pdf"
            dest_filename = f"{name}{source_ext}"
            dest_pdf = self._projects_dir / dest_filename
            
            # If file already exists, append a number
            if dest_pdf.exists() and str(pdf_source) != str(dest_pdf):
                base = dest_pdf.stem
                ext = dest_pdf.suffix
                counter = 1
                while dest_pdf.exists():
                    dest_pdf = self._projects_dir / f"{base}_{counter}{ext}"
                    counter += 1
            
            if str(pdf_source) != str(dest_pdf):
                shutil.copy2(str(pdf_source), str(dest_pdf))
            pdf_path_final = str(dest_pdf.resolve())
        else:
            # Use source path as-is (may be placeholder)
            pdf_path_final = str(pdf_source)

        now = self._now()
        conn = self._connect()
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        try:
            cursor = conn.execute(
                """
                INSERT INTO projects (name, pdf_path, chosen_character, created_at, updated_at, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, pdf_path_final, initial_character, now, now, meta_json),
            )
            conn.commit()
            # Get the ID of the newly inserted project
            project_id = cursor.lastrowid
        except sqlite3.IntegrityError as e:
            raise ProjectLibraryError(f"Project name must be unique: {name}") from e

        # Return the project using the ID we just got
        return self.get_project(project_id)

    def list_projects(self) -> List[Project]:
        rows = self._connect().execute(
            "SELECT * FROM projects ORDER BY updated_at DESC, name ASC"
        ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def get_project(self, project_id: int) -> Project:
        row = self._connect().execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not row:
            raise ProjectLibraryError(f"Project not found: id={project_id}")
        return self._row_to_project(row)

    def get_project_by_name(self, name: str) -> Project:
        row = self._connect().execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            raise ProjectLibraryError(f"Project not found: name={name}")
        return self._row_to_project(row)

    def rename_project(self, project_id: int, new_name: str) -> Project:
        new_name = new_name.strip()
        if not new_name:
            raise ProjectLibraryError("New name is required.")
        now = self._now()
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, now, project_id),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise ProjectLibraryError(f"Project name already exists: {new_name}")
        return self.get_project(project_id)

    def set_project_character(self, project_id: int, character: Optional[str]) -> Project:
        now = self._now()
        self._connect().execute(
            "UPDATE projects SET chosen_character = ?, updated_at = ? WHERE id = ?",
            (character, now, project_id),
        )
        self._connect().commit()
        return self.get_project(project_id)

    def update_pdf_path(
        self, project_id: int, new_pdf_path: Union[str, Path], copy_into_library: bool = False
    ) -> Project:
        new_pdf = Path(new_pdf_path).expanduser().resolve()
        if not new_pdf.exists():
            raise ProjectLibraryError(f"PDF not found: {new_pdf}")

        pdf_path_final = str(new_pdf)
        if copy_into_library:
            proj = self.get_project(project_id)
            # Copy file directly into projects folder
            dest_filename = new_pdf.name
            dest_pdf = self._projects_dir / dest_filename
            
            # If file already exists and it's not the same file, append a number
            if dest_pdf.exists() and str(new_pdf) != str(dest_pdf):
                base = dest_pdf.stem
                ext = dest_pdf.suffix
                counter = 1
                while dest_pdf.exists():
                    dest_pdf = self._projects_dir / f"{base}_{counter}{ext}"
                    counter += 1
            
            if str(new_pdf) != str(dest_pdf):
                shutil.copy2(str(new_pdf), str(dest_pdf))
            pdf_path_final = str(dest_pdf.resolve())

        now = self._now()
        self._connect().execute(
            "UPDATE projects SET pdf_path = ?, updated_at = ? WHERE id = ?",
            (pdf_path_final, now, project_id),
        )
        self._connect().commit()
        return self.get_project(project_id)

    def update_meta(self, project_id: int, updater: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Project:
        proj = self.get_project(project_id)
        new_meta = updater(dict(proj.meta) if proj.meta else {})
        now = self._now()
        self._connect().execute(
            "UPDATE projects SET meta_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(new_meta, ensure_ascii=False), now, project_id),
        )
        self._connect().commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: int, remove_file: bool = False) -> None:
        proj = self.get_project(project_id)
        self._connect().execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._connect().commit()
        if remove_file:
            self._remove_project_storage(proj)
            self._remove_project_attachments(proj)

    # ---------- Utilities ----------

    def ensure_project_subdir(self, project: Project) -> Path:
        """
        Deprecated: Returns the projects directory. Projects are now files, not folders.
        Kept for backward compatibility.
        """
        return self._projects_dir

    def _remove_project_storage(self, proj: Project) -> None:
        """Remove project files and directories from the projects folder."""
        meta = proj.meta or {}
        candidates: Set[Path] = set()

        folder_hint = meta.get("folder_path")
        if folder_hint:
            candidates.add(Path(folder_hint).expanduser())

        expected_folder = (self._projects_dir / proj.name)
        candidates.add(expected_folder)

        pdf_path = Path(proj.pdf_path).expanduser()
        if pdf_path.exists():
            if pdf_path.is_file() and self._is_within_projects_dir(pdf_path):
                try:
                    pdf_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if pdf_path.parent.exists():
                candidates.add(pdf_path.parent)

        projects_dir_resolved = None
        try:
            projects_dir_resolved = self._projects_dir.resolve()
        except Exception:
            return

        unique_dirs: Set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            if not resolved.exists() or not resolved.is_dir():
                continue
            unique_dirs.add(resolved)

        for directory in sorted(unique_dirs, key=lambda p: len(p.parts), reverse=True):
            if directory == projects_dir_resolved:
                continue
            if projects_dir_resolved not in directory.parents:
                continue
            try:
                shutil.rmtree(directory, ignore_errors=True)
            except Exception:
                pass

    def _remove_project_attachments(self, proj: Project) -> None:
        """Remove saved attachments associated with a project."""
        prefix = f"{proj.id}_"
        try:
            for attachment in self._attach_dir.glob(f"{prefix}*"):
                try:
                    if attachment.is_dir():
                        shutil.rmtree(attachment, ignore_errors=True)
                    else:
                        attachment.unlink(missing_ok=True)
                except Exception:
                    continue
        except Exception:
            pass

    def _is_within_projects_dir(self, path: Path) -> bool:
        """Check if a path is located within the projects directory."""
        try:
            target = path.resolve()
            projects_dir_resolved = self._projects_dir.resolve()
        except Exception:
            return False
        return projects_dir_resolved in target.parents or target == projects_dir_resolved

    def attachment_path(self, project: Project, filename: str) -> Path:
        """
        Place for arbitrary files tied to a project:
        <library>/.rehearsal/attachments/<project_id>_<filename>
        """
        safe = f"{project.id}_{filename}"
        return (self._attach_dir / safe).resolve()
    
    def voice_presets_dir(self) -> Path:
        """
        Get the voice presets directory for this library.
        Preset files placed here will work across all projects in the library.
        """
        return self._voice_presets_dir
    
    def resources_dir(self) -> Path:
        """
        Get the resources directory for this library.
        Shared web links and resources accessible across all projects.
        """
        return self._resources_dir

    def scan_and_register_pdfs(self, subdirs: Optional[List[str]] = None) -> List[Project]:
        """
        Scan projects/ folder for folders and register them as projects.
        Only folders directly in projects/ become projects (folder name = project name).
        Also removes invalid projects from the database.
        Returns list of newly added projects.
        """
        added: List[Project] = []
        # Only scan the projects folder
        if not self._projects_dir.exists():
            return added
        
        # Valid project file extensions (for finding files within folders)
        VALID_EXTENSIONS = {'.pdf', '.txt', '.doc', '.docx', '.rtf', '.fountain', '.fdx'}
        
        # Folders to exclude (metadata, system folders, etc.) - case-insensitive
        EXCLUDED_NAMES = {
            'file_structure', 'icon', 'icon\r', 'icon\n', '.ds_store', 'thumbs.db',
            'desktop.ini', '.gitignore', '.gitkeep', 'customizations', '.rehearsal',
            'male_student_sides_lbr'  # Add this specific one
        }
        
        # Get list of valid folder names in projects/
        valid_folder_names = set()
        for item_path in self._projects_dir.iterdir():
            # Skip hidden items
            if item_path.name.startswith('.'):
                continue
            
            # Skip excluded items (case-insensitive)
            if item_path.name.lower() in EXCLUDED_NAMES:
                continue
            
            # Only process folders
            if item_path.is_dir():
                valid_folder_names.add(item_path.name)
        
        # Clean up invalid projects from database
        all_projects = self.list_projects()
        for proj in all_projects:
            # Remove if project name is in exclusion list (case-insensitive)
            if proj.name.lower() in EXCLUDED_NAMES:
                try:
                    self.delete_project(proj.id, remove_file=False)
                except Exception:
                    pass
            # Remove if folder doesn't exist in projects/
            elif proj.name not in valid_folder_names:
                try:
                    self.delete_project(proj.id, remove_file=False)
                except Exception:
                    pass
        
        # Only scan for folders (each folder = a project)
        for item_path in self._projects_dir.iterdir():
            # Skip hidden items
            if item_path.name.startswith('.'):
                continue
            
            # Skip excluded items (case-insensitive)
            if item_path.name.lower() in EXCLUDED_NAMES:
                continue
            
            # Only process folders, skip files
            if not item_path.is_dir():
                continue
            
            project_name = item_path.name
            
            # Check if project already exists
            try:
                self.get_project_by_name(project_name)
                continue  # Already registered
            except ProjectLibraryError:
                pass  # Not registered yet, continue
            
            # Look for a project file in the folder
            project_file = None
            for ext in VALID_EXTENSIONS:
                # Try common names first
                for common_name in ['script', 'main', project_name.lower()]:
                    candidate = item_path / f"{common_name}{ext}"
                    if candidate.exists():
                        project_file = candidate
                        break
                if project_file:
                    break
            
            # If no common name found, search for any valid file
            if not project_file:
                for file_path in item_path.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in VALID_EXTENSIONS:
                        # Skip excluded files
                        if file_path.name.lower() not in EXCLUDED_NAMES:
                            project_file = file_path
                            break
            
            # Create project with found file, or use folder as placeholder
            try:
                if project_file:
                    added.append(self.create_project(
                        name=project_name,
                        pdf_source_path=project_file,
                        copy_into_library=False,  # File is already in the projects folder
                        initial_character=None,
                        meta={"imported_via_scan": True, "folder_path": str(item_path), "file_path": str(project_file)}
                    ))
                else:
                    # Create placeholder project for folder without valid file
                    placeholder_path = item_path / "script.pdf"
                    added.append(self.create_project(
                        name=project_name,
                        pdf_source_path=placeholder_path,
                        copy_into_library=False,  # Placeholder
                        initial_character=None,
                        meta={"imported_via_scan": True, "folder_path": str(item_path), "is_placeholder": True}
                    ))
            except ProjectLibraryError as e:
                # If registration fails, skip this folder
                continue
        
        return added

# ----------------------------
# High-level facade
# ----------------------------

class ProjectManager:
    """
    Combines Config (remembers last-chosen library) and ProjectLibrary.
    """
    def __init__(self, app_name: str = "ActorRehearsal"):
        self.config = Config(app_name=app_name)
        self.library: Optional[ProjectLibrary] = None
        if self.config.library_path:
            try:
                self.set_library(self.config.library_path)
            except Exception:
                self.library = None

    def set_library(self, library_path: Union[str, Path]) -> None:
        resolved_path = ProjectLibrary.resolve_library_root(library_path)
        lib = ProjectLibrary(resolved_path)
        # swap-in
        if self.library:
            self.library.close()
        self.library = lib
        self.config.library_path = str(lib.root)

    def clear_library(self) -> None:
        if self.library:
            self.library.close()
        self.library = None
        self.config.library_path = None

    # Convenience proxies

    def create(self, name: str, pdf_path: Union[str, Path], copy_into_library: bool = True,
               initial_character: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> Project:
        self._require_lib()
        return self.library.create_project(name, pdf_path, copy_into_library, None, initial_character, meta)

    def list(self) -> List[Project]:
        self._require_lib()
        return self.library.list_projects()

    def get(self, project_id: int) -> Project:
        self._require_lib()
        return self.library.get_project(project_id)

    def get_by_name(self, name: str) -> Project:
        self._require_lib()
        return self.library.get_project_by_name(name)

    def set_character(self, project_id: int, character: Optional[str]) -> Project:
        self._require_lib()
        return self.library.set_project_character(project_id, character)

    def rename(self, project_id: int, new_name: str) -> Project:
        self._require_lib()
        return self.library.rename_project(project_id, new_name)

    def replace_pdf(self, project_id: int, new_pdf_path: Union[str, Path], copy_into_library: bool = False) -> Project:
        self._require_lib()
        return self.library.update_pdf_path(project_id, new_pdf_path, copy_into_library)

    def update_meta(self, project_id: int, updater: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Project:
        self._require_lib()
        return self.library.update_meta(project_id, updater)

    def delete(self, project_id: int, remove_file: bool = False) -> None:
        self._require_lib()
        self.library.delete_project(project_id, remove_file)

    def scan(self, subdirs: Optional[List[str]] = None) -> List[Project]:
        self._require_lib()
        return self.library.scan_and_register_pdfs(subdirs)
    
    def voice_presets_dir(self) -> Optional[Path]:
        """Get the voice presets directory for the current library."""
        if self.library:
            return self.library.voice_presets_dir()
        return None

    def _require_lib(self) -> None:
        if not self.library:
            raise ProjectLibraryError("No library set. Call set_library(<folder_path>) first.")