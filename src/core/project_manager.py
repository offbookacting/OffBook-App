# core/project_manager.py
from __future__ import annotations
import os
import sqlite3
import json
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

# ----------------------------
# Data models
# ----------------------------

@dataclass
class Project:
    id: int
    name: str
    pdf_path: str                 # absolute path to the script PDF
    chosen_character: str | None
    created_at: float             # epoch seconds
    updated_at: float             # epoch seconds
    meta: dict[str, Any]          # arbitrary JSON (e.g., cached parse hints)

# ----------------------------
# Paths and Config
# ----------------------------

def mac_app_support_dir(app_name: str = "ActorRehearsal") -> Path:
    base = Path.home() / "Library" / "Application Support" / app_name
    base.mkdir(parents=True, exist_ok=True)
    return base

class Config:
    """Stores app-level settings (e.g., last library path)."""
    def __init__(self, app_name: str = "ActorRehearsal"):
        self._app_dir = mac_app_support_dir(app_name)
        self._config_path = self._app_dir / "config.json"
        self._data: dict[str, Any] = {}
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
    def library_path(self) -> str | None:
        return self._data.get("library_path")

    @library_path.setter
    def library_path(self, p: str | None) -> None:
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
        .rehearsal/
          projects.db
          attachments/           # optional future assets per project
        <project_name>/
          script.pdf             # default copied script location (optional)
          meta.json              # optional project-local metadata (future)
    """
    DB_SUBDIR = ".rehearsal"
    DB_FILE = "projects.db"
    ATTACH_DIR = "attachments"

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise ProjectLibraryError(f"Library folder does not exist: {self.root}")
        if not self.root.is_dir():
            raise ProjectLibraryError(f"Not a directory: {self.root}")
        self._db_dir = self.root / self.DB_SUBDIR
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._attach_dir = self._db_dir / self.ATTACH_DIR
        self._attach_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._db_dir / self.DB_FILE
        self._conn: sqlite3.Connection | None = None
        self._ensure_db()

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
        pdf_source_path: str | Path,
        copy_into_library: bool = True,
        project_subdir: str | None = None,
        initial_character: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Project:
        """
        Register a new project. Optionally copy the PDF into <library>/<project_name>/script.pdf.
        """
        name = name.strip()
        if not name:
            raise ProjectLibraryError("Project name is required.")
        pdf_source = Path(pdf_source_path).expanduser().resolve()
        if not pdf_source.exists():
            raise ProjectLibraryError(f"PDF not found: {pdf_source}")

        # Decide destination
        if copy_into_library:
            subdir = project_subdir or name
            project_dir = self.root / subdir
            project_dir.mkdir(parents=True, exist_ok=True)
            dest_pdf = project_dir / "script.pdf"
            if str(pdf_source) != str(dest_pdf):
                shutil.copy2(str(pdf_source), str(dest_pdf))
            pdf_path_final = str(dest_pdf.resolve())
        else:
            pdf_path_final = str(pdf_source)

        now = self._now()
        conn = self._connect()
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        try:
            conn.execute(
                """
                INSERT INTO projects (name, pdf_path, chosen_character, created_at, updated_at, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, pdf_path_final, initial_character, now, now, meta_json),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            raise ProjectLibraryError(f"Project name must be unique: {name}") from e

        return self.get_project_by_name(name)

    def list_projects(self) -> list[Project]:
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

    def set_project_character(self, project_id: int, character: str | None) -> Project:
        now = self._now()
        self._connect().execute(
            "UPDATE projects SET chosen_character = ?, updated_at = ? WHERE id = ?",
            (character, now, project_id),
        )
        self._connect().commit()
        return self.get_project(project_id)

    def update_pdf_path(
        self, project_id: int, new_pdf_path: str | Path, copy_into_library: bool = False
    ) -> Project:
        new_pdf = Path(new_pdf_path).expanduser().resolve()
        if not new_pdf.exists():
            raise ProjectLibraryError(f"PDF not found: {new_pdf}")

        pdf_path_final = str(new_pdf)
        if copy_into_library:
            proj = self.get_project(project_id)
            proj_dir = Path(proj.pdf_path).parent if proj.pdf_path.endswith("script.pdf") else (self.root / proj.name)
            proj_dir.mkdir(parents=True, exist_ok=True)
            dest_pdf = proj_dir / "script.pdf"
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

    def update_meta(self, project_id: int, updater: Callable[[dict[str, Any]], dict[str, Any]]) -> Project:
        proj = self.get_project(project_id)
        new_meta = updater(dict(proj.meta) if proj.meta else {})
        now = self._now()
        self._connect().execute(
            "UPDATE projects SET meta_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(new_meta, ensure_ascii=False), now, project_id),
        )
        self._connect().commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: int, remove_folder: bool = False) -> None:
        proj = self.get_project(project_id)
        self._connect().execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._connect().commit()
        if remove_folder:
            # Remove <library>/<project_name>/ if exists and appears owned by app
            candidate = Path(proj.pdf_path).parent
            try:
                if candidate.is_dir() and candidate.parent == self.root:
                    shutil.rmtree(candidate, ignore_errors=True)
            except Exception:
                pass

    # ---------- Utilities ----------

    def ensure_project_subdir(self, project: Project) -> Path:
        """
        Ensure a per-project folder exists at <library>/<project_name>/.
        """
        pdir = self.root / project.name
        pdir.mkdir(parents=True, exist_ok=True)
        return pdir

    def attachment_path(self, project: Project, filename: str) -> Path:
        """
        Place for arbitrary files tied to a project:
        <library>/.rehearsal/attachments/<project_id>_<filename>
        """
        safe = f"{project.id}_{filename}"
        return (self._attach_dir / safe).resolve()

    def scan_and_register_pdfs(self, subdirs: list[str] | None = None) -> list[Project]:
        """
        Optional helper: scan library for PDFs not in DB and register them.
        Uses folder name as project name. Returns list of newly added.
        """
        added: list[Project] = []
        roots = [self.root] if not subdirs else [self.root / s for s in subdirs]
        for r in roots:
            if not r.exists():
                continue
            for pdf in r.rglob("*.pdf"):
                # Skip internal DB area
                if str(self._db_dir) in str(pdf.resolve()):
                    continue
                # Infer name
                name = pdf.parent.name
                try:
                    self.get_project_by_name(name)
                    continue
                except ProjectLibraryError:
                    pass
                try:
                    added.append(self.create_project(
                        name=name,
                        pdf_source_path=pdf,
                        copy_into_library=False,
                        initial_character=None,
                        meta={"imported_via_scan": True}
                    ))
                except ProjectLibraryError:
                    # If name collides, append suffix
                    suffix = f"-{pdf.stem}"
                    try:
                        added.append(self.create_project(
                            name=name + suffix,
                            pdf_source_path=pdf,
                            copy_into_library=False,
                            initial_character=None,
                            meta={"imported_via_scan": True}
                        ))
                    except ProjectLibraryError:
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
        self.library: ProjectLibrary | None = None
        if self.config.library_path:
            try:
                self.set_library(self.config.library_path)
            except Exception:
                self.library = None

    def set_library(self, library_path: str | Path) -> None:
        lib = ProjectLibrary(library_path)
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

    def create(self, name: str, pdf_path: str | Path, copy_into_library: bool = True,
               initial_character: str | None = None, meta: dict[str, Any] | None = None) -> Project | None:
        self.library = self._require_lib()
        return self.library.create_project(name, pdf_path, copy_into_library, None, initial_character, meta)

    def list(self) -> list[Project]:
        self.library = self._require_lib()
        return self.library.list_projects()

    def get(self, project_id: int) -> Project:
        self.library = self._require_lib()
        return self.library.get_project(project_id)

    def get_by_name(self, name: str) -> Project:
        self.library = self._require_lib()
        return self.library.get_project_by_name(name)

    def set_character(self, project_id: int, character: str | None) -> Project:
        self.library = self._require_lib()
        return self.library.set_project_character(project_id, character)

    def rename(self, project_id: int, new_name: str) -> Project:
        self.library = self._require_lib()
        return self.library.rename_project(project_id, new_name)

    def replace_pdf(self, project_id: int, new_pdf_path: str | Path, copy_into_library: bool = False) -> Project:
        self.library = self._require_lib()
        return self.library.update_pdf_path(project_id, new_pdf_path, copy_into_library)

    def update_meta(self, project_id: int, updater: Callable[[dict[str, Any]], dict[str, Any]]) -> Project:
        self.library = self._require_lib()
        return self.library.update_meta(project_id, updater)

    def delete(self, project_id: int, remove_folder: bool = False) -> None:
        self.library = self._require_lib()
        self.library.delete_project(project_id, remove_folder)

    def scan(self, subdirs: list[str] | None = None) -> list[Project]:
        self.library = self._require_lib()
        return self.library.scan_and_register_pdfs(subdirs)

    def _require_lib(self) -> ProjectLibrary:
        if isinstance(self.library, ProjectLibrary):
            return self.library
        else:
            raise ProjectLibraryError("No library set. Call set_library(<folder_path>) first.")