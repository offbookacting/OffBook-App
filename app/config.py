# app/config.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reuse the same app-support location as core.project_manager
try:
    from core.project_manager import mac_app_support_dir
except Exception:
    # Fallback if imported early in bootstrap
    import os
    import platform
    def mac_app_support_dir(app_name: str = "ActorRehearsal") -> Path:
        """Cross-platform app support directory fallback."""
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
        """Save config to disk. Silently fails if disk is full or permission denied."""
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except (OSError, IOError, PermissionError) as e:
            # Silently fail if disk is full, permission denied, or other I/O errors
            # The setting will still work in memory, just won't persist
            pass

    def _defaults(self) -> Dict[str, Any]:
        return {
            "window": {"width": 1200, "height": 800, "maximized": False},
            "editor": {
                "font_family": "Courier Prime",
                "font_size": 12,
                "wrap": False,
            },
            "highlight": {"color": "#FFF59D", "weight": 600},
            "recent_libraries": [],   # purely UI convenience
            "recent_projects": [],    # list[str] of project names
            "tts": {
                "engine": "piper",
                "model_path": "",
                "speaker": None,
            },
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

    # ---------- TTS ----------

    def tts_config(self) -> dict:
        return dict(self._data.get("tts", {}))

    def tts_model_path(self) -> Optional[str]:
        cfg = self._data.setdefault("tts", {})
        path = cfg.get("model_path")
        if not path:
            return None
        
        # Validate that the path is not pointing to a demo/test file or venv
        path_str = str(path)
        if any(excluded in path_str for excluded in [".venv", "venv", "site-packages", "logreg_iris", "datasets"]):
            # Invalid path detected - clear it from config
            self._data["tts"]["model_path"] = ""
            self._save()
            return None
        
        # Check if file exists
        path_obj = Path(path)
        if not path_obj.exists():
            return None
        
        return path

    def set_tts_model_path(self, path: str) -> None:
        """Set TTS model path with validation."""
        path_str = str(path).strip()
        
        # Validate that the path is not pointing to a demo/test file or venv
        if any(excluded in path_str for excluded in [".venv", "venv", "site-packages", "logreg_iris", "datasets"]):
            raise ValueError(
                f"Invalid model path: {path_str}\n\n"
                "The path points to a demo file or virtual environment directory.\n"
                "Please select a valid Piper TTS voice model (.onnx file)."
            )
        
        # Validate that the file exists
        path_obj = Path(path_str)
        if not path_obj.exists():
            raise ValueError(f"Model file not found: {path_str}")
        
        self._data.setdefault("tts", {})
        self._data["tts"]["model_path"] = path_str
        self._save()

    def tts_speaker(self) -> Optional[int]:
        cfg = self._data.setdefault("tts", {})
        return cfg.get("speaker")

    def set_tts_speaker(self, speaker: Optional[int]) -> None:
        self._data.setdefault("tts", {})
        self._data["tts"]["speaker"] = speaker
        self._save()

    # ---------- Character Colors ----------

    def character_colors(self) -> Dict[str, Optional[str]]:
        """
        Get all character color mappings.
        Returns dict mapping character name (uppercase) to color hex string or None for no highlight.
        """
        colors = self._data.get("character_colors", {})
        return {k: v if v != "No Highlight" else None for k, v in colors.items()}

    def get_character_color(self, character: str) -> Optional[str]:
        """
        Get color for a specific character.
        Returns color hex string or None for no highlight.
        """
        colors = self._data.get("character_colors", {})
        color = colors.get(character.upper().strip())
        if color == "No Highlight":
            return None
        return color

    def set_character_color(self, character: str, color: Optional[str]) -> None:
        """
        Set color for a character.
        Pass None or "No Highlight" to remove highlighting for the character.
        """
        colors = self._data.setdefault("character_colors", {})
        char_key = character.upper().strip()
        if color is None or color == "No Highlight":
            colors[char_key] = "No Highlight"
        else:
            colors[char_key] = str(color)
        self._save()

    # ---------- Custom Colors ----------

    def custom_colors(self) -> List[str]:
        """Get list of custom colors added by the user."""
        return list(self._data.get("custom_colors", []))

    def add_custom_color(self, color: str) -> None:
        """Add a custom color to the preset list."""
        custom = self._data.setdefault("custom_colors", [])
        color_str = str(color).upper()
        # Don't add if it's already in the list
        if color_str not in [c.upper() for c in custom]:
            custom.append(color_str)
            self._save()

    # ---------- Rehearse Highlighting Options ----------

    def rehearse_highlighting_options(self) -> Dict[str, bool]:
        """Get rehearse highlighting options."""
        options = self._data.get("rehearse_highlighting_options", {})
        return {
            "enable_highlighting": options.get("enable_highlighting", True),
            "highlight_character_names": options.get("highlight_character_names", False),
            "highlight_parentheticals": options.get("highlight_parentheticals", False),
            "smoosh_hieroglyphs": options.get("smoosh_hieroglyphs", False),
        }

    def set_rehearse_highlighting_option(self, option_name: str, value: bool) -> None:
        """Set a rehearse highlighting option."""
        options = self._data.setdefault("rehearse_highlighting_options", {})
        options[option_name] = bool(value)
        self._save()

    # ---------- Rehearse Alignment Options ----------

    def rehearse_alignment_options(self) -> Dict[str, str]:
        """Get rehearse alignment options. Returns dict with keys: character_names, dialogue, narrator, everything_else."""
        options = self._data.get("rehearse_alignment_options", {})
        return {
            "character_names": options.get("character_names", "center"),
            "dialogue": options.get("dialogue", "center"),
            "narrator": options.get("narrator", "left"),
            "everything_else": options.get("everything_else", "left"),
        }

    def set_rehearse_alignment_option(self, option_name: str, alignment: str) -> None:
        """Set a rehearse alignment option. alignment should be 'left', 'center', or 'right'."""
        if alignment not in ["left", "center", "right"]:
            raise ValueError(f"Invalid alignment: {alignment}. Must be 'left', 'center', or 'right'.")
        options = self._data.setdefault("rehearse_alignment_options", {})
        options[option_name] = alignment
        self._save()