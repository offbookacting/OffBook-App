# core/file_state_manager.py
"""
File state manager - stores user preferences per file (zoom, page, scroll position, etc.)
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Dict, Any
import time


class FileStateManager:
    """
    Manages per-file state information like zoom level, page number, scroll position.
    Stores state in a JSON file in the project directory.
    """
    
    STATE_FILE = "file_state.json"
    
    def __init__(self, project_root: Path):
        """
        Initialize file state manager.
        
        Args:
            project_root: Root directory of the project where state will be stored
        """
        self.project_root = Path(project_root).resolve()
        self.state_file = self.project_root / self.STATE_FILE
        self._state: Dict[str, Dict[str, Any]] = {}
        self._load()
    
    def _load(self) -> None:
        """Load state from JSON file."""
        if self.state_file.exists():
            try:
                content = self.state_file.read_text(encoding="utf-8")
                self._state = json.loads(content)
            except Exception as e:
                print(f"Error loading file state: {e}")
                self._state = {}
        else:
            self._state = {}
    
    def _save(self) -> None:
        """Save state to JSON file."""
        try:
            # Ensure project root exists
            self.project_root.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first, then replace
            temp_file = self.state_file.with_suffix(".tmp")
            temp_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
            temp_file.replace(self.state_file)
        except Exception as e:
            print(f"Error saving file state: {e}")
    
    def _get_file_key(self, file_path: Path) -> str:
        """Get a unique key for a file path."""
        # Use resolved absolute path as key
        return str(Path(file_path).resolve())
    
    def get_zoom_level(self, file_path: Path, default: float = 1.0) -> float:
        """Get saved zoom level for a file."""
        file_key = self._get_file_key(file_path)
        file_state = self._state.get(file_key, {})
        return file_state.get("zoom", default)
    
    def set_zoom_level(self, file_path: Path, zoom: float) -> None:
        """Save zoom level for a file."""
        file_key = self._get_file_key(file_path)
        if file_key not in self._state:
            self._state[file_key] = {}
        self._state[file_key]["zoom"] = zoom
        self._state[file_key]["updated_at"] = time.time()
        self._save()
    
    def get_page_number(self, file_path: Path, default: int = 0) -> int:
        """Get saved page number for a file (0-indexed)."""
        file_key = self._get_file_key(file_path)
        file_state = self._state.get(file_key, {})
        return file_state.get("page", default)
    
    def set_page_number(self, file_path: Path, page: int) -> None:
        """Save page number for a file (0-indexed)."""
        file_key = self._get_file_key(file_path)
        if file_key not in self._state:
            self._state[file_key] = {}
        self._state[file_key]["page"] = page
        self._state[file_key]["updated_at"] = time.time()
        self._save()
    
    def get_read_scroll_position(self, file_path: Path, default: int = 0) -> int:
        """Get saved scroll position for read tab (scrollbar value)."""
        file_key = self._get_file_key(file_path)
        file_state = self._state.get(file_key, {})
        read_state = file_state.get("read_tab", {})
        return read_state.get("scroll_position", default)
    
    def set_read_scroll_position(self, file_path: Path, scroll_position: int) -> None:
        """Save scroll position for read tab."""
        file_key = self._get_file_key(file_path)
        if file_key not in self._state:
            self._state[file_key] = {}
        if "read_tab" not in self._state[file_key]:
            self._state[file_key]["read_tab"] = {}
        self._state[file_key]["read_tab"]["scroll_position"] = scroll_position
        self._state[file_key]["updated_at"] = time.time()
        self._save()
    
    def get_read_cursor_position(self, file_path: Path, default: int = 0) -> int:
        """Get saved cursor position for read tab (text cursor position)."""
        file_key = self._get_file_key(file_path)
        file_state = self._state.get(file_key, {})
        read_state = file_state.get("read_tab", {})
        return read_state.get("cursor_position", default)
    
    def set_read_cursor_position(self, file_path: Path, cursor_position: int) -> None:
        """Save cursor position for read tab."""
        file_key = self._get_file_key(file_path)
        if file_key not in self._state:
            self._state[file_key] = {}
        if "read_tab" not in self._state[file_key]:
            self._state[file_key]["read_tab"] = {}
        self._state[file_key]["read_tab"]["cursor_position"] = cursor_position
        self._state[file_key]["updated_at"] = time.time()
        self._save()
    
    def get_custom_state(self, file_path: Path, key: str, default: Any = None) -> Any:
        """Get custom state value for a file."""
        file_key = self._get_file_key(file_path)
        file_state = self._state.get(file_key, {})
        return file_state.get(key, default)
    
    def set_custom_state(self, file_path: Path, key: str, value: Any) -> None:
        """Set custom state value for a file."""
        file_key = self._get_file_key(file_path)
        if file_key not in self._state:
            self._state[file_key] = {}
        self._state[file_key][key] = value
        self._state[file_key]["updated_at"] = time.time()
        self._save()
    
    def get_file_state(self, file_path: Path) -> Dict[str, Any]:
        """Get all state for a file."""
        file_key = self._get_file_key(file_path)
        return self._state.get(file_key, {}).copy()
    
    def clear_file_state(self, file_path: Path) -> None:
        """Clear all state for a file."""
        file_key = self._get_file_key(file_path)
        if file_key in self._state:
            del self._state[file_key]
            self._save()

