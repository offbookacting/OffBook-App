# app/config.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

# Reuse the same app-support location as core.project_manager
try:
    from core.project_manager import mac_app_support_dir
except Exception:
    # Fallback if imported early in bootstrap
    def mac_app_support_dir(app_name: str = "ActorRehearsal") -> Path:
        base = Path.home() / "Library" / "Application Support" / app_name
        base.mkdir(parents=True, exist_ok=True)
        return base


class AppConfig:
    """
    GUI-focused config (window, editor, highlight, recents).
    Library path is managed by core.project_manager.Config.
    Stored at: ~/Library/Application Support/ActorRehearsal/ui_config.json
    """

    def __init__(self, app_name: str = "ActorRehearsal"):
        self._dir = mac_app_support_dir(app_name)
        self._path = self._dir / "ui_config.json"
        self._data: Dict[str, Any] = {}
        self._load()

    # ---------- I/O ----------

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        if not self._data:
            self._data = self._defaults()
            self._save()

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _defaults(self) -> Dict[str, Any]:
        return {
            "window": {"width": 1200, "height": 800, "maximized": False},
            "editor": {
                "font_family": "Menlo",
                "font_size": 12,
                "wrap": False,
            },
            "highlight": {"color": "#FFF59D", "weight": 600},
            "recent_libraries": [],   # purely UI convenience
            "recent_projects": [],    # list[str] of project names
        }

    # ---------- Window ----------

    def window_geometry(self) -> dict:
        return dict(self._data.get("window", {}))

    def set_window_geometry(self, width: int, height: int, maximized: bool) -> None:
        self._data.setdefault("window", {})
        self._data["window"].update({"width": int(width), "height": int(height), "maximized": bool(maximized)})
        self._save()

    # ---------- Editor ----------

    def editor_prefs(self) -> dict:
        return dict(self._data.get("editor", {}))

    def set_editor_prefs(self, font_family: Optional[str] = None, font_size: Optional[int] = None, wrap: Optional[bool] = None) -> None:
        ed = self._data.setdefault("editor", {})
        if font_family is not None:
            ed["font_family"] = str(font_family)
        if font_size is not None:
            ed["font_size"] = int(font_size)
        if wrap is not None:
            ed["wrap"] = bool(wrap)
        self._save()

    # ---------- Highlight ----------

    def highlight_style(self) -> dict:
        return dict(self._data.get("highlight", {}))

    def set_highlight_style(self, color: Optional[str] = None, weight: Optional[int] = None) -> None:
        hl = self._data.setdefault("highlight", {})
        if color is not None:
            hl["color"] = str(color)
        if weight is not None:
            hl["weight"] = int(weight)
        self._save()

    # ---------- Recents ----------

    def add_recent_library(self, path: str, max_items: int = 5) -> None:
        lst = self._data.setdefault("recent_libraries", [])
        path = str(Path(path).expanduser())
        if path in lst:
            lst.remove(path)
        lst.insert(0, path)
        del lst[max_items:]
        self._save()

    def recent_libraries(self) -> list[str]:
        return list(self._data.get("recent_libraries", []))

    def add_recent_project(self, name: str, max_items: int = 10) -> None:
        lst = self._data.setdefault("recent_projects", [])
        name = str(name).strip()
        if name in lst:
            lst.remove(name)
        lst.insert(0, name)
        del lst[max_items:]
        self._save()

    def recent_projects(self) -> list[str]:
        return list(self._data.get("recent_projects", []))