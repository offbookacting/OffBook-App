# app/project_browser.py
"""
Project browser screen - shows all projects and allows selection.
Opens on startup before entering the main workspace.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Callable
import json
import os
import sys
import subprocess

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QGridLayout, QFrame, QDialog, QInputDialog, QMenu
)

from core.project_manager import ProjectManager, ProjectLibraryError, Project, ProjectLibrary


class ProjectBrowser(QWidget):
    """Project browser widget that shows all projects."""
    
    project_selected = pyqtSignal(int)  # emits project_id
    project_created = pyqtSignal(int)  # emits project_id
    library_required = pyqtSignal()  # emitted when library is needed
    
    def __init__(self, project_manager: ProjectManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.pm = project_manager
        self._setup_ui()
        self._refresh_projects()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Header
        header = QHBoxLayout()
        title = QLabel("Scene Partner")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        
        # Library info
        self.lbl_library = QLabel("No library selected")
        self.lbl_library.setStyleSheet("color: #666;")
        header.addWidget(self.lbl_library)
        
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._on_refresh)
        btn_refresh.setToolTip("Refresh project list from library folder")
        header.addWidget(btn_refresh)
        
        btn_create_lib = QPushButton("Create Library…")
        btn_create_lib.clicked.connect(self._on_choose_library)
        header.addWidget(btn_create_lib)
        
        btn_select_existing = QPushButton("Select Existing Library…")
        btn_select_existing.clicked.connect(self._on_select_existing_library)
        header.addWidget(btn_select_existing)
        
        layout.addLayout(header)
        
        # Projects section
        projects_label = QLabel("Projects")
        projects_font = QFont()
        projects_font.setPointSize(16)
        projects_font.setBold(True)
        projects_label.setFont(projects_font)
        layout.addWidget(projects_label)
        
        # Project list
        self.list_projects = QListWidget()
        self.list_projects.setSpacing(5)
        self.list_projects.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_projects.itemDoubleClicked.connect(self._on_project_double_clicked)
        self.list_projects.itemSelectionChanged.connect(self.selection_changed)
        self.list_projects.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_projects.customContextMenuRequested.connect(self._on_context_menu)
        # Connect to model's rowsMoved signal for drag-and-drop reordering
        self.list_projects.model().rowsMoved.connect(self._on_items_reordered)
        # Set flow layout to wrap items
        self.list_projects.setFlow(QListWidget.Flow.LeftToRight)
        self.list_projects.setWrapping(True)
        self.list_projects.setStyleSheet("""
            QListWidget::item {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                margin: 2px;
            }
            QListWidget::item:hover {
                background-color: #D3D3D3;
            }
            QListWidget::item:selected {
                background-color: #2196F3;
                color: white;
                border: 2px solid #1976D2;
            }
            QListWidget::item:selected:!active {
                background-color: #2196F3;
                color: white;
            }
        """)
        layout.addWidget(self.list_projects, stretch=1)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_new = QPushButton("New Project…")
        self.btn_new.clicked.connect(self._on_new_project)
        self.btn_new.setEnabled(False)
        btn_layout.addWidget(self.btn_new)
        
        self.btn_add_referenced = QPushButton("Reference Project from Other Library…")
        self.btn_add_referenced.clicked.connect(self._on_add_referenced_project)
        self.btn_add_referenced.setEnabled(False)
        btn_layout.addWidget(self.btn_add_referenced)
        
        self.btn_open = QPushButton("Open Project")
        self.btn_open.clicked.connect(self._on_open_project)
        self.btn_open.setEnabled(False)
        btn_layout.addWidget(self.btn_open)
        
        self.btn_rename = QPushButton("Rename Project")
        self.btn_rename.clicked.connect(self._on_rename_project)
        self.btn_rename.setEnabled(False)
        btn_layout.addWidget(self.btn_rename)
        
        self.btn_delete = QPushButton("Delete Project")
        self.btn_delete.clicked.connect(self._on_delete_project)
        self.btn_delete.setEnabled(False)
        btn_layout.addWidget(self.btn_delete)
        
        layout.addLayout(btn_layout)
        
        # Update library label
        if self.pm.config.library_path:
            self.lbl_library.setText(f"Library: {Path(self.pm.config.library_path).name}")
            self.btn_new.setEnabled(True)
            self.btn_add_referenced.setEnabled(True)
        else:
            self.lbl_library.setText("No library selected")
    
    def _refresh_projects(self, scan_filesystem: bool = False) -> None:
        """Refresh the project list from the database.
        
        Args:
            scan_filesystem: If True, scan the filesystem for new PDF files and register them.
                            If False, just list projects from the database.
        """
        self.list_projects.clear()
        
        if not self.pm.config.library_path:
            return
        
        try:
            # Optionally scan filesystem for new files (only when explicitly requested, like on refresh button)
            if scan_filesystem:
                self.pm.scan()
            
            # List projects from database
            projects = self.pm.list()
            
            # Load project order from customizations
            project_order = self._load_project_order()
            
            # Sort projects according to saved order
            if project_order:
                # Create a mapping of project IDs to their order
                order_map = {pid: idx for idx, pid in enumerate(project_order)}
                # Sort projects: first by saved order, then by name for items not in order
                projects.sort(key=lambda p: (order_map.get(p.id, 9999), p.name))
            
            if not projects:
                # Show helpful message if no projects found
                item = QListWidgetItem("(No projects found - add files to the projects folder or click 'New Project')")
                item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
                self.list_projects.addItem(item)
            else:
                for proj in projects:
                    # Check if this is a referenced project
                    is_referenced = proj.meta and proj.meta.get("is_referenced_project", False)
                    display_name = proj.name
                    if is_referenced:
                        display_name = f"{proj.name} (referenced project)"
                    
                    item = QListWidgetItem(display_name)
                    item.setData(Qt.ItemDataRole.UserRole, proj.id)
                    # Add metadata as tooltip
                    pdf_path = Path(proj.pdf_path)
                    tooltip = f"File: {pdf_path.name}\n"
                    if pdf_path.exists():
                        tooltip += f"Location: {pdf_path.parent.name}/\n"
                    if is_referenced:
                        tooltip += "Type: Referenced Project (external folder)\n"
                    if proj.chosen_character:
                        tooltip += f"Character: {proj.chosen_character}"
                    item.setToolTip(tooltip)
                    # Set size hint to wrap around text (padding + text width + some margin)
                    font_metrics = self.list_projects.fontMetrics()
                    text_width = font_metrics.horizontalAdvance(display_name)
                    # Add padding (10px left + 10px right = 20px) and extra margin to prevent cutoff
                    item_width = text_width + 50  # Increased margin to prevent text cutoff
                    item_height = font_metrics.height() + 30  # Increased height for better spacing
                    item.setSizeHint(QSize(item_width, item_height))
                    self.list_projects.addItem(item)
        except ProjectLibraryError as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def _on_choose_library(self) -> None:
        """Handle library selection - show dialog to create or select existing library."""
        from app.library_creation_dialog import LibraryCreationDialog
        
        # First, try to create a new library
        dialog = LibraryCreationDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.library_path:
                try:
                    self.pm.set_library(str(dialog.library_path))
                    
                    # Check if voices need to be installed
                    if self.pm.library and self.pm.library.needs_voice_installation():
                        from app.voice_install_dialog import VoiceInstallDialog
                        models_dir, presets_dir = self.pm.library.get_voice_directories()
                        install_dialog = VoiceInstallDialog(models_dir, presets_dir, self)
                        install_dialog.exec()
                        # Clear the flag
                        self.pm.library._voices_need_installation = False
                    
                    self.lbl_library.setText(f"Library: {dialog.library_path.name}")
                    self.btn_new.setEnabled(True)
                    self.btn_add_referenced.setEnabled(True)
                    self._refresh_projects()
                except ProjectLibraryError as e:
                    QMessageBox.critical(self, "Error", str(e))
        else:
            # If user cancelled, offer to select existing library directly
            reply = QMessageBox.question(
                self,
                "Select Existing Library",
                "Would you like to select an existing library folder?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._prompt_select_existing_library()
    
    def _on_add_referenced_project(self) -> None:
        """Handle adding a project folder from outside the library."""
        if not self.pm.library:
            QMessageBox.warning(self, "No Library", "Please select a library first.")
            return
        
        # Prompt user to select a folder
        default_path = Path.home() / "Documents"
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Project Folder",
            str(default_path)
        )
        
        if not folder_path:
            return
        
        folder_path = Path(folder_path).expanduser().resolve()
        
        if not folder_path.exists() or not folder_path.is_dir():
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid folder.")
            return
        
        # Check if this folder is already a referenced project
        existing_projects = self.pm.list()
        for proj in existing_projects:
            if proj.meta and proj.meta.get("is_referenced_project", False):
                referenced_path = Path(proj.meta.get("referenced_folder_path", ""))
                if referenced_path.resolve() == folder_path.resolve():
                    QMessageBox.warning(
                        self,
                        "Already Added",
                        f"This folder is already added as project '{proj.name}'."
                    )
                    return
        
        # Ask for project name
        project_name = folder_path.name
        name, ok = QInputDialog.getText(
            self,
            "Add Referenced Project",
            "Enter project name:",
            text=project_name
        )
        
        if not ok or not name.strip():
            return
        
        project_name = name.strip()
        
        # Check if project name already exists
        try:
            self.pm.get_by_name(project_name)
            QMessageBox.warning(
                self,
                "Duplicate Name",
                f"A project named '{project_name}' already exists. Please choose a different name."
            )
            return
        except ProjectLibraryError:
            pass  # Name doesn't exist, which is good
        
        try:
            # Find a PDF or other script file in the folder to use as the project file
            script_file = None
            valid_extensions = {'.pdf', '.txt', '.doc', '.docx', '.rtf', '.fountain', '.fdx'}
            
            # Look for common script file names first
            for ext in valid_extensions:
                for common_name in ['script', 'main', project_name.lower()]:
                    candidate = folder_path / f"{common_name}{ext}"
                    if candidate.exists() and candidate.is_file():
                        script_file = candidate
                        break
                if script_file:
                    break
            
            # If no common name found, search for any valid file
            if not script_file:
                for file_path in folder_path.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in valid_extensions:
                        script_file = file_path
                        break
            
            # If still no file found, create a placeholder
            if not script_file:
                script_file = folder_path / "script.pdf"
            
            # Create project with referenced project metadata
            meta = {
                "is_referenced_project": True,
                "referenced_folder_path": str(folder_path),
                "folder_path": str(folder_path)
            }
            
            proj = self.pm.create(
                project_name,
                str(script_file),
                copy_into_library=False,  # Don't copy, just reference
                initial_character=None,
                meta=meta
            )
            
            # Refresh projects list
            self._refresh_projects(scan_filesystem=False)
            
            # Add new project to the end of the order
            project_order = self._load_project_order()
            if proj.id not in project_order:
                project_order.append(proj.id)
                # Save the updated order
                customizations_dir = Path(self.pm.library.root) / self.pm.library.CUSTOMIZATIONS_DIR
                customizations_dir.mkdir(parents=True, exist_ok=True)
                order_file = customizations_dir / "project_order.json"
                with open(order_file, 'w', encoding='utf-8') as f:
                    json.dump({'project_ids': project_order}, f, indent=2)
            
            # Select the new project in the list
            for i in range(self.list_projects.count()):
                item = self.list_projects.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == proj.id:
                    self.list_projects.setCurrentItem(item)
                    break
            
            # Emit signal to open the project
            self.project_created.emit(proj.id)
        except ProjectLibraryError as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def _on_new_project(self) -> None:
        """Handle new project creation - creates a project file directly in the library."""
        from PyQt6.QtWidgets import QInputDialog
        
        # Ask for project name
        name, ok = QInputDialog.getText(
            self,
            "New Project",
            "Enter project name:",
            text=""
        )
        
        if not ok or not name.strip():
            return
        
        project_name = name.strip()
        
        try:
            # Create project folder directly in the library's projects folder
            if not self.pm.library:
                QMessageBox.warning(self, "No Library", "Please select a library first.")
                return
            
            # Create a folder for the project in the projects directory
            projects_dir = Path(self.pm.library.root) / self.pm.library.PROJECTS_DIR
            project_folder = projects_dir / project_name
            
            # If folder already exists, append a number
            if project_folder.exists():
                base = project_name
                counter = 1
                while project_folder.exists():
                    project_folder = projects_dir / f"{base}_{counter}"
                    counter += 1
                project_name = project_folder.name  # Update project name if we had to append a number
            
            # Create the project folder
            project_folder.mkdir(parents=True, exist_ok=True)
            
            # Create a placeholder PDF path (file doesn't exist yet, but will be created when user adds a file)
            placeholder_pdf = project_folder / "script.pdf"
            
            # Create project entry pointing to the placeholder PDF path
            # Use copy_into_library=False since we're just creating a placeholder
            proj = self.pm.create(
                project_name, str(placeholder_pdf), copy_into_library=False, initial_character=None
            )
            
            # Refresh projects list from database (don't scan filesystem - project is already in DB)
            self._refresh_projects(scan_filesystem=False)
            
            # Add new project to the end of the order
            project_order = self._load_project_order()
            if proj.id not in project_order:
                project_order.append(proj.id)
                # Save the updated order
                customizations_dir = Path(self.pm.library.root) / self.pm.library.CUSTOMIZATIONS_DIR
                customizations_dir.mkdir(parents=True, exist_ok=True)
                order_file = customizations_dir / "project_order.json"
                with open(order_file, 'w', encoding='utf-8') as f:
                    json.dump({'project_ids': project_order}, f, indent=2)
            
            # Select the new project in the list
            for i in range(self.list_projects.count()):
                item = self.list_projects.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == proj.id:
                    self.list_projects.setCurrentItem(item)
                    break
            
            # Emit signal to open the project - use the project object returned from create()
            # which should be valid since it was just committed to the database
            self.project_created.emit(proj.id)
        except ProjectLibraryError as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_select_existing_library(self) -> None:
        """Prompt the user to select an existing library directory."""
        self._prompt_select_existing_library()

    def _prompt_select_existing_library(self) -> None:
        """Show a directory picker and apply the chosen library path."""
        default_path = (
            Path(self.pm.config.library_path).parent
            if self.pm.config.library_path else Path.home() / "Documents"
        )
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Existing Library Folder",
            str(default_path)
        )
        if path:
            self._apply_library_path(self._resolve_library_root(Path(path)))

    def _apply_library_path(self, library_path: Path) -> None:
        """Validate and apply the chosen library path."""
        try:
            # Validate it's a valid library
            ProjectLibrary(library_path)
            self.pm.set_library(str(library_path))

            # Check if voices need to be installed
            if self.pm.library and self.pm.library.needs_voice_installation():
                from app.voice_install_dialog import VoiceInstallDialog
                models_dir, presets_dir = self.pm.library.get_voice_directories()
                install_dialog = VoiceInstallDialog(models_dir, presets_dir, self)
                install_dialog.exec()
                # Clear the flag
                self.pm.library._voices_need_installation = False

            self.lbl_library.setText(f"Library: {library_path.name}")
            self.btn_new.setEnabled(True)
            self.btn_add_referenced.setEnabled(True)
            self._refresh_projects()
        except ProjectLibraryError as e:
            QMessageBox.critical(self, "Error", f"Invalid library folder:\n{e}")
    
    def _resolve_library_root(self, selected_path: Path) -> Path:
        """Resolve the actual library root from a user-selected path."""
        return ProjectLibrary.resolve_library_root(selected_path)
    
    def _on_open_project(self) -> None:
        """Handle project opening."""
        item = self.list_projects.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "Please select a project first.")
            return
        
        project_id = item.data(Qt.ItemDataRole.UserRole)
        self.project_selected.emit(project_id)
    
    def _on_project_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on project."""
        project_id = item.data(Qt.ItemDataRole.UserRole)
        self.project_selected.emit(project_id)
    
    def _on_delete_project(self) -> None:
        """Handle project deletion."""
        item = self.list_projects.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "Please select a project first.")
            return
        
        project_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this project? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.pm.delete(project_id, remove_file=True)
                # Save updated order after deletion
                self._save_project_order()
                self._refresh_projects(scan_filesystem=False)
            except ProjectLibraryError as e:
                QMessageBox.critical(self, "Error", str(e))
    
    def _on_refresh(self) -> None:
        """Handle refresh button click."""
        if not self.pm.config.library_path:
            QMessageBox.information(
                self,
                "No Library",
                "Please select a library folder first."
            )
            return
        
        # Scan filesystem for new files when user explicitly clicks refresh
        self._refresh_projects(scan_filesystem=True)
        
        # Count actual projects (exclude placeholder items)
        project_count = 0
        for i in range(self.list_projects.count()):
            item = self.list_projects.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                project_count += 1
        
        if project_count > 0:
            QMessageBox.information(
                self,
                "Refreshed",
                f"Project list refreshed.\nFound {project_count} project(s)."
            )
        else:
            QMessageBox.information(
                self,
                "Refreshed",
                "Project list refreshed.\nNo projects found in library folder."
            )
    
    def selection_changed(self) -> None:
        """Update button states based on selection."""
        has_selection = self.list_projects.currentItem() is not None
        self.btn_open.setEnabled(has_selection)
        self.btn_rename.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
    
    def _on_context_menu(self, position) -> None:
        """Show context menu for project list."""
        item = self.list_projects.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        
        act_open = menu.addAction("Open")
        act_open.triggered.connect(self._on_open_project)
        
        act_rename = menu.addAction("Rename")
        act_rename.triggered.connect(self._on_rename_project)
        
        menu.addSeparator()

        act_show_location = menu.addAction("Show File Location")
        act_show_location.triggered.connect(self._on_show_file_location)
        
        menu.addSeparator()
        
        act_delete = menu.addAction("Delete")
        act_delete.triggered.connect(self._on_delete_project)
        
        menu.exec(self.list_projects.mapToGlobal(position))
    
    def _on_rename_project(self) -> None:
        """Handle project renaming."""
        item = self.list_projects.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "Please select a project first.")
            return
        
        project_id = item.data(Qt.ItemDataRole.UserRole)
        current_name = item.text()
        
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Project",
            "Enter new project name:",
            text=current_name
        )
        
        if not ok or not new_name.strip() or new_name.strip() == current_name:
            return
        
        try:
            # Rename the project in the database
            proj = self.pm.rename(project_id, new_name.strip())
            
            # Rename the folder in the filesystem
            projects_dir = Path(self.pm.library.root) / self.pm.library.PROJECTS_DIR
            old_folder = projects_dir / current_name
            new_folder = projects_dir / new_name.strip()
            
            if old_folder.exists() and old_folder.is_dir():
                if new_folder.exists():
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"A folder named '{new_name.strip()}' already exists."
                    )
                    return
                old_folder.rename(new_folder)
                
                # Update the PDF path in the database if it was in the old folder
                if proj.pdf_path:
                    old_pdf_path = Path(proj.pdf_path)
                    if old_folder in old_pdf_path.parents or str(old_folder) in str(old_pdf_path):
                        # Update the path to point to the new folder
                        new_pdf_path = new_folder / old_pdf_path.name
                        # Update the PDF path in the database
                        self.pm.library.update_pdf_path(proj.id, str(new_pdf_path), copy_into_library=False)
            
            # Refresh the project list
            self._refresh_projects(scan_filesystem=False)
            
            # Select the renamed project
            for i in range(self.list_projects.count()):
                item = self.list_projects.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == proj.id:
                    self.list_projects.setCurrentItem(item)
                    break
        except ProjectLibraryError as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def _on_show_file_location(self) -> None:
        """Reveal the selected project's files in the system file browser."""
        item = self.list_projects.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "Please select a project first.")
            return

        project_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            proj = self.pm.get(project_id)
        except ProjectLibraryError as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        pdf_path = Path(proj.pdf_path).expanduser()
        target = pdf_path if pdf_path.exists() else pdf_path.parent

        if not target.exists():
            if self.pm.library:
                target = Path(self.pm.library.root) / self.pm.library.PROJECTS_DIR / proj.name
            else:
                QMessageBox.warning(self, "Warning", "File location could not be determined.")
                return

        try:
            if sys.platform == "darwin":
                if target.is_file():
                    subprocess.run(["open", "-R", str(target)], check=False)
                else:
                    subprocess.run(["open", str(target)], check=False)
            elif sys.platform.startswith("win"):
                os.startfile(str(target if target.is_dir() else target.parent))
            else:
                subprocess.run(
                    ["xdg-open", str(target if target.is_dir() else target.parent)],
                    check=False,
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open location:\n{e}")
    
    def _on_items_reordered(self, parent, start, end, destination, row) -> None:
        """Handle project reordering via drag and drop."""
        # Save the new order
        self._save_project_order()
    
    def _load_project_order(self) -> list[int]:
        """Load project order from customizations folder."""
        if not self.pm.library:
            return []
        
        try:
            customizations_dir = Path(self.pm.library.root) / self.pm.library.CUSTOMIZATIONS_DIR
            order_file = customizations_dir / "project_order.json"
            
            if order_file.exists():
                with open(order_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('project_ids', [])
        except Exception:
            pass
        
        return []
    
    def _save_project_order(self) -> None:
        """Save project order to customizations folder."""
        if not self.pm.library:
            return
        
        try:
            # Get current order of project IDs from the list widget
            project_ids = []
            for i in range(self.list_projects.count()):
                item = self.list_projects.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole):
                    project_ids.append(item.data(Qt.ItemDataRole.UserRole))
            
            # Save to customizations folder
            customizations_dir = Path(self.pm.library.root) / self.pm.library.CUSTOMIZATIONS_DIR
            customizations_dir.mkdir(parents=True, exist_ok=True)
            order_file = customizations_dir / "project_order.json"
            
            with open(order_file, 'w', encoding='utf-8') as f:
                json.dump({'project_ids': project_ids}, f, indent=2)
        except Exception as e:
            # Non-critical error, just log it
            print(f"Failed to save project order: {e}")

