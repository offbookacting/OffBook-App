# core/file_manager.py
"""
Hierarchical file organization system for projects (Scrivener-style).
Supports drag-and-drop, folders, and nested organization.
"""
from __future__ import annotations
import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from enum import Enum


class FileItemType(Enum):
    FILE = "file"
    FOLDER = "folder"
    PDF = "pdf"
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


@dataclass
class FileItem:
    """Represents a file or folder in the project hierarchy."""
    id: str
    name: str
    type: FileItemType
    path: str  # absolute path
    parent_id: Optional[str] = None
    children: List[str] = None  # list of child item IDs
    metadata: Dict[str, Any] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "path": self.path,
            "parent_id": self.parent_id,
            "children": self.children,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileItem:
        return cls(
            id=data["id"],
            name=data["name"],
            type=FileItemType(data["type"]),
            path=data["path"],
            parent_id=data.get("parent_id"),
            children=data.get("children", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )


class FileManager:
    """
    Manages hierarchical file organization for a project.
    Stores structure in JSON and manages physical files in project directory.
    """
    
    STRUCTURE_FILE = "file_structure.json"
    HIDDEN_STRUCTURE_FILE = ".file_structure.json"
    FILES_DIR = "files"
    
    def __init__(self, project_root: Union[str, Path], use_root_as_files_dir: bool = False):
        self.project_root = Path(project_root).expanduser().resolve()
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.is_referenced_project = use_root_as_files_dir
        
        # Determine the correct files directory path
        if use_root_as_files_dir:
            # For referenced projects, use project_root directly as files_dir
            self.files_dir = self.project_root
        elif self.project_root.name == self.FILES_DIR:
            # project_root is already the files directory, use it directly
            self.files_dir = self.project_root
        else:
            # Always check if "files" subdirectory already exists under project_root
            # Expected path: library/projects/project_name/files
            expected_files_dir = self.project_root / self.FILES_DIR
            if expected_files_dir.exists() and expected_files_dir.is_dir():
                # Use existing "files" directory
                self.files_dir = expected_files_dir
            else:
                # Create new "files" directory at expected location
                self.files_dir = expected_files_dir
                self.files_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure files_dir exists (should already exist from above, but this is a safety check)
        if not self.files_dir.exists():
            self.files_dir.mkdir(parents=True, exist_ok=True)
        
        # Use hidden filename for referenced projects
        structure_filename = self.HIDDEN_STRUCTURE_FILE if use_root_as_files_dir else self.STRUCTURE_FILE
        self.structure_path = self.project_root / structure_filename
        self._items: Dict[str, FileItem] = {}
        self._root_id: Optional[str] = None
        self._load()
    
    def _load(self) -> None:
        """Load file structure from JSON."""
        # Check for both hidden and non-hidden versions (for backward compatibility)
        structure_paths = [self.structure_path]
        if self.is_referenced_project:
            # Also check non-hidden version in case it was created before
            structure_paths.append(self.project_root / self.STRUCTURE_FILE)
        else:
            # Also check hidden version in case it was migrated
            structure_paths.append(self.project_root / self.HIDDEN_STRUCTURE_FILE)
        
        for path in structure_paths:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self._items = {
                        item_id: FileItem.from_dict(item_data)
                        for item_id, item_data in data.get("items", {}).items()
                    }
                    self._root_id = data.get("root_id")
                    # For referenced projects, migrate non-hidden files to hidden versions
                    if self.is_referenced_project and path != self.structure_path:
                        # Found non-hidden version, migrate to hidden
                        try:
                            import shutil
                            shutil.move(str(path), str(self.structure_path))
                        except Exception:
                            # If migration fails, just use the existing file
                            self.structure_path = path
                    elif path != self.structure_path:
                        # For non-referenced projects, just use the found file
                        self.structure_path = path
                    return
                except Exception:
                    continue
        
        # No valid structure file found - initialize empty
        self._items = {}
        self._root_id = None
        
        # Create root folder
        import time
        root = FileItem(
            id="root",
            name="Root",
            type=FileItemType.FOLDER,
            path=str(self.files_dir),
            parent_id=None,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._items["root"] = root
        self._root_id = "root"
        self._save()
    
    def _save(self) -> None:
        """Save file structure to JSON."""
        data = {
            "items": {item_id: item.to_dict() for item_id, item in self._items.items()},
            "root_id": self._root_id,
        }
        self.structure_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def _generate_id(self) -> str:
        """Generate a unique ID for a file item."""
        import uuid
        return str(uuid.uuid4())
    
    def _get_item_type(self, path: Path) -> FileItemType:
        """Determine FileItemType from file path."""
        if path.is_dir():
            return FileItemType.FOLDER
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return FileItemType.PDF
        elif suffix in [".txt", ".md", ".doc", ".docx"]:
            return FileItemType.TEXT
        elif suffix in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"]:
            return FileItemType.IMAGE
        elif suffix in [".mp3", ".wav", ".m4a", ".aac"]:
            return FileItemType.AUDIO
        elif suffix in [".mp4", ".mov", ".avi", ".mkv"]:
            return FileItemType.VIDEO
        else:
            return FileItemType.FILE
    
    def add_file(self, source_path: Union[str, Path], parent_id: Optional[str] = None, name: Optional[str] = None, copy_file: bool = True) -> FileItem:
        """Add a file to the hierarchy."""
        import time
        source = Path(source_path).expanduser().resolve()
        if not source.exists():
            raise ValueError(f"Source file does not exist: {source}")
        
        parent_id = parent_id or self._root_id
        parent = self._items.get(parent_id)
        if not parent or parent.type != FileItemType.FOLDER:
            raise ValueError(f"Invalid parent: {parent_id}")
        
        # Determine destination
        dest_name = name or source.name
        dest_path = Path(parent.path) / dest_name
        
        # Check if item already exists with this path
        existing = self.find_item_by_path(str(dest_path))
        if existing:
            return existing  # Return existing item instead of creating duplicate
        
        # Copy or link file
        if copy_file:
            if source.is_file():
                # Don't copy if source and dest are the same
                if str(source.resolve()) != str(dest_path.resolve()):
                    shutil.copy2(str(source), str(dest_path))
            elif source.is_dir():
                shutil.copytree(str(source), str(dest_path), dirs_exist_ok=True)
        else:
            # Just reference the existing file (for project PDF)
            dest_path = source
        
        # Create item
        item = FileItem(
            id=self._generate_id(),
            name=dest_name,
            type=self._get_item_type(dest_path if copy_file else source),
            path=str((dest_path if copy_file else source).resolve()),
            parent_id=parent_id,
            created_at=time.time(),
            updated_at=time.time(),
        )
        
        self._items[item.id] = item
        parent.children.append(item.id)
        parent.updated_at = time.time()
        self._save()
        
        return item
    
    def create_folder(self, name: str, parent_id: Optional[str] = None) -> FileItem:
        """Create a new folder in the hierarchy."""
        import time
        parent_id = parent_id or self._root_id
        parent = self._items.get(parent_id)
        if not parent or parent.type != FileItemType.FOLDER:
            raise ValueError(f"Invalid parent: {parent_id}")
        
        folder_path = Path(parent.path) / name
        folder_path.mkdir(parents=True, exist_ok=True)
        
        folder = FileItem(
            id=self._generate_id(),
            name=name,
            type=FileItemType.FOLDER,
            path=str(folder_path.resolve()),
            parent_id=parent_id,
            created_at=time.time(),
            updated_at=time.time(),
        )
        
        self._items[folder.id] = folder
        parent.children.append(folder.id)
        parent.updated_at = time.time()
        self._save()
        
        return folder
    
    def move_item(self, item_id: str, new_parent_id: str) -> FileItem:
        """Move an item to a new parent."""
        import time
        item = self._items.get(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        new_parent = self._items.get(new_parent_id)
        if not new_parent or new_parent.type != FileItemType.FOLDER:
            raise ValueError(f"Invalid new parent: {new_parent_id}")
        
        # Remove from old parent
        if item.parent_id:
            old_parent = self._items[item.parent_id]
            if item_id in old_parent.children:
                old_parent.children.remove(item_id)
                old_parent.updated_at = time.time()
        
        # Add to new parent
        item.parent_id = new_parent_id
        item.updated_at = time.time()
        if item_id not in new_parent.children:
            new_parent.children.append(item_id)
        new_parent.updated_at = time.time()
        
        # Move physical file/folder
        current_path = Path(item.path)
        new_path = Path(new_parent.path) / item.name
        if current_path.exists():
            if current_path.resolve() != new_path.resolve():
                if new_path.exists():
                    # If destination exists, append suffix to avoid clobbering
                    suffix = f"_{int(time.time())}"
                    new_path = new_path.with_name(new_path.stem + suffix + new_path.suffix)
                shutil.move(str(current_path), str(new_path))
                item.path = str(new_path.resolve())
        
        self._save()
        return item
    
    def rename_item(self, item_id: str, new_name: str) -> FileItem:
        """Rename an item."""
        import time
        item = self._items.get(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        old_path = Path(item.path)
        new_path = old_path.parent / new_name
        
        if old_path.exists():
            old_path.rename(new_path)
        
        item.name = new_name
        item.path = str(new_path.resolve())
        item.updated_at = time.time()
        self._save()
        
        return item
    
    def delete_item(self, item_id: str, remove_files: bool = True) -> None:
        """Delete an item and optionally remove its files."""
        item = self._items.get(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        if item_id == self._root_id:
            raise ValueError("Cannot delete root folder")
        
        # Recursively delete children
        for child_id in list(item.children):
            self.delete_item(child_id, remove_files=remove_files)
        
        # Remove from parent
        if item.parent_id:
            parent = self._items[item.parent_id]
            if item_id in parent.children:
                parent.children.remove(item_id)
                parent.updated_at = item.updated_at
        
        # Remove physical file/folder
        if remove_files and Path(item.path).exists():
            if Path(item.path).is_dir():
                shutil.rmtree(item.path, ignore_errors=True)
            else:
                Path(item.path).unlink(missing_ok=True)
        
        # Remove from items
        del self._items[item_id]
        self._save()
    
    def get_item(self, item_id: str) -> Optional[FileItem]:
        """Get an item by ID."""
        return self._items.get(item_id)
    
    def get_root(self) -> FileItem:
        """Get the root folder."""
        return self._items[self._root_id]
    
    def get_children(self, parent_id: Optional[str] = None) -> List[FileItem]:
        """Get children of a parent item."""
        parent_id = parent_id or self._root_id
        parent = self._items.get(parent_id)
        if not parent:
            return []
        return [self._items[child_id] for child_id in parent.children if child_id in self._items]
    
    def get_all_items(self) -> List[FileItem]:
        """Get all items in the hierarchy."""
        return list(self._items.values())
    
    def find_item_by_path(self, path: Union[str, Path]) -> Optional[FileItem]:
        """Find an item by its file path."""
        path_str = str(Path(path).resolve())
        for item in self._items.values():
            if item.path == path_str:
                return item
        return None

