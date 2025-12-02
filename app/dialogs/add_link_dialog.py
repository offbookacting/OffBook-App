# app/dialogs/add_link_dialog.py
"""
Dialog for adding web links - paste URL, search the internet, or use library resources.
"""
from pathlib import Path
from typing import Optional
import json
import urllib.parse
import shutil
import subprocess
import sys
from app.utils import reveal_in_finder

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QRadioButton, QButtonGroup, QMessageBox, QListWidget,
    QListWidgetItem, QInputDialog, QGroupBox, QSplitter, QWidget
)


class AddLinkDialog(QDialog):
    """Dialog for adding web links."""
    
    def __init__(self, project_root: Path, library_resources_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.library_resources_dir = library_resources_dir
        self.url: Optional[str] = None
        self.link_name: Optional[str] = None
        self.added_file_path: Optional[Path] = None  # Track file added from resources
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the UI."""
        self.setWindowTitle("Add Link")
        self.setModal(True)
        self.resize(700, 500)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("Add Web Link")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        # Create splitter for resources and link options
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Library Resources (if available)
        if self.library_resources_dir and self.library_resources_dir.exists():
            resources_widget = self._create_resources_widget()
            splitter.addWidget(resources_widget)
        
        # Right side: Add New Link
        link_widget = self._create_link_widget()
        splitter.addWidget(link_widget)
        
        # Set sizes
        if self.library_resources_dir and self.library_resources_dir.exists():
            splitter.setSizes([300, 400])
        
        layout.addWidget(splitter, stretch=1)
        
        # OK and Cancel buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
    
    def _create_resources_widget(self) -> QGroupBox:
        """Create the library resources section."""
        group = QGroupBox("Library Resources")
        layout = QVBoxLayout(group)
        
        # Info label
        info = QLabel("Shared resources available across all projects:")
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(info)
        
        # Resources list
        self.resources_list = QListWidget()
        self.resources_list.itemDoubleClicked.connect(self._on_resource_double_clicked)
        self.resources_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.resources_list.customContextMenuRequested.connect(self._on_resource_context_menu)
        layout.addWidget(self.resources_list)
        
        # Refresh resources list
        self._refresh_resources_list()
        
        # Buttons for resources
        btn_layout = QHBoxLayout()
        
        btn_add_to_project = QPushButton("Add to Project")
        btn_add_to_project.clicked.connect(self._on_add_resource_to_project)
        btn_layout.addWidget(btn_add_to_project)
        
        btn_new_resource = QPushButton("New Resource")
        btn_new_resource.clicked.connect(self._on_new_resource)
        btn_layout.addWidget(btn_new_resource)
        
        layout.addLayout(btn_layout)
        
        return group
    
    def _create_link_widget(self) -> QWidget:
        """Create the add new link section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # Group title
        group_title = QLabel("Add New Link to Project")
        group_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(group_title)
        
        # Option 1: Paste Link
        self.radio_paste = QRadioButton("Paste Link")
        self.radio_paste.setChecked(True)
        layout.addWidget(self.radio_paste)
        
        paste_layout = QHBoxLayout()
        paste_layout.setContentsMargins(30, 0, 0, 0)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter or paste URL (e.g., https://example.com)")
        self.url_input.installEventFilter(self)
        paste_layout.addWidget(self.url_input)
        
        btn_paste = QPushButton("Paste")
        btn_paste.clicked.connect(self._on_paste_clicked)
        paste_layout.addWidget(btn_paste)
        layout.addLayout(paste_layout)
        
        # Option 2: Search the Internet
        self.radio_search = QRadioButton("Search the Internet")
        layout.addWidget(self.radio_search)
        
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(30, 0, 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search query")
        self.search_input.installEventFilter(self)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Link name input
        layout.addSpacing(10)
        name_label = QLabel("Link Name (optional):")
        layout.addWidget(name_label)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name for this link")
        layout.addWidget(self.name_input)
        
        # Button group for radio buttons
        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.radio_paste)
        self.button_group.addButton(self.radio_search)
        self.button_group.buttonClicked.connect(self._on_option_changed)
        self._on_option_changed(self.radio_paste)
        
        # OK button
        layout.addStretch()
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.btn_ok = QPushButton("Add to Project")
        self.btn_ok.clicked.connect(self._on_ok_clicked)
        button_layout.addWidget(self.btn_ok)
        
        layout.addLayout(button_layout)
        
        return widget
    
    def _on_option_changed(self, button):
        """Handle radio button change."""
        is_paste = button == self.radio_paste
        if is_paste:
            self.url_input.setFocus()
        else:
            self.search_input.setFocus()
    
    def _on_paste_clicked(self):
        """Paste from clipboard into URL input."""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.url_input.setText(text)
            self._set_option(True)
    
    def _on_ok_clicked(self):
        """Validate and accept the dialog."""
        if self.radio_paste.isChecked():
            # Paste link option
            url = self.url_input.text().strip()
            if not url:
                QMessageBox.warning(self, "Error", "Please enter a URL.")
                return
            
            # Add protocol if missing
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            self.url = url
            
            # Get link name (use URL if not provided)
            name = self.name_input.text().strip()
            if not name:
                # Extract domain name from URL
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    name = parsed.netloc or url
                except:
                    name = url
            
            self.link_name = name
            
        else:
            # Search option
            query = self.search_input.text().strip()
            if not query:
                QMessageBox.warning(self, "Error", "Please enter a search query.")
                return
            
            # Create Google search URL
            encoded_query = urllib.parse.quote(query)
            self.url = f"https://www.google.com/search?q={encoded_query}"
            
            # Get link name (use query if not provided)
            name = self.name_input.text().strip()
            if not name:
                name = f"Search: {query}"
            
            self.link_name = name
        
        # Save the link to a .web file
        try:
            self._save_web_link()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save link:\n{e}")
    
    def _set_option(self, paste: bool) -> None:
        """Programmatically switch between paste/search options."""
        if paste:
            if not self.radio_paste.isChecked():
                self.radio_paste.setChecked(True)
                self._on_option_changed(self.radio_paste)
        else:
            if not self.radio_search.isChecked():
                self.radio_search.setChecked(True)
                self._on_option_changed(self.radio_search)
    
    def _submit_paste_via_enter(self) -> None:
        """Handle Enter pressed in the URL input."""
        if not self.isVisible():
            return
        self._set_option(True)
        self._on_ok_clicked()
    
    def _submit_search_via_enter(self) -> None:
        """Handle Enter pressed in the search input."""
        if not self.isVisible():
            return
        self._set_option(False)
        self._on_ok_clicked()
    
    def _save_web_link(self):
        """Save the link as a .html file in the files directory."""
        # Determine the correct files directory path
        # Check if project_root already ends with "files" to avoid nested "files/files"
        if self.project_root.name == "files":
            files_dir = self.project_root
        else:
            # Check if "files" subdirectory already exists (expected: library/projects/project_name/files)
            expected_files_dir = self.project_root / "files"
            if expected_files_dir.exists() and expected_files_dir.is_dir():
                # Use existing "files" directory
                files_dir = expected_files_dir
            else:
                # Create new "files" directory
                files_dir = expected_files_dir
                files_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure files_dir exists (safety check)
        if not files_dir.exists():
            files_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename from link name
        filename = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in self.link_name)
        filename = filename.strip()
        if not filename:
            filename = "link"
        
        # Ensure unique filename
        base_filename = filename
        counter = 1
        html_file = files_dir / f"{filename}.html"
        while html_file.exists():
            filename = f"{base_filename}_{counter}"
            html_file = files_dir / f"{filename}.html"
            counter += 1
        
        # Create HTML content with meta redirect
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0; url={self.url}">
    <title>{self.link_name}</title>
</head>
<body>
    <p>Redirecting to <a href="{self.url}">{self.link_name}</a>...</p>
</body>
</html>"""
        
        html_file.write_text(html_content, encoding="utf-8")
        
        # Store the path so it can be opened automatically
        self.added_file_path = html_file
    
    def _refresh_resources_list(self):
        """Refresh the library resources list."""
        if not self.library_resources_dir or not self.library_resources_dir.exists():
            return
        
        self.resources_list.clear()
        
        # Load all .html files from resources directory
        for html_file in sorted(self.library_resources_dir.glob("*.html")):
            try:
                content = html_file.read_text(encoding="utf-8")
                # Extract title and URL from HTML
                name, url = self._parse_html_link(content, html_file.stem)
                
                item = QListWidgetItem(f"{name}")
                item.setData(Qt.ItemDataRole.UserRole, str(html_file))
                item.setToolTip(f"{name}\n{url}")
                self.resources_list.addItem(item)
            except Exception as e:
                print(f"Error loading resource {html_file}: {e}")
    
    def _on_resource_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on resource - add to project."""
        self._on_add_resource_to_project()
    
    def _parse_html_link(self, html_content: str, default_name: str = "Link") -> tuple[str, str]:
        """Parse HTML to extract title and URL."""
        import re
        
        # Extract title
        title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
        name = title_match.group(1).strip() if title_match else default_name
        
        # Extract URL from meta refresh
        url_match = re.search(r'content="0;\s*url=([^"]+)"', html_content, re.IGNORECASE)
        url = url_match.group(1).strip() if url_match else ""
        
        return name, url
    
    def _on_add_resource_to_project(self):
        """Add selected resource to project."""
        current_item = self.resources_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a resource to add.")
            return
        
        resource_path = Path(current_item.data(Qt.ItemDataRole.UserRole))
        if not resource_path.exists():
            QMessageBox.warning(self, "Error", "Resource file not found.")
            return
        
        # Copy resource to project files directory
        try:
            # Place in project_root / files (not in a Websites subdirectory)
            # Determine the correct files directory path
            # Check if project_root already ends with "files" to avoid nested "files/files"
            if self.project_root.name == "files":
                files_dir = self.project_root
            else:
                # Check if "files" subdirectory already exists (expected: library/projects/project_name/files)
                expected_files_dir = self.project_root / "files"
                if expected_files_dir.exists() and expected_files_dir.is_dir():
                    # Use existing "files" directory
                    files_dir = expected_files_dir
                else:
                    # Create new "files" directory
                    files_dir = expected_files_dir
                    files_dir.mkdir(parents=True, exist_ok=True)
            
            # Ensure files_dir exists (safety check)
            if not files_dir.exists():
                files_dir.mkdir(parents=True, exist_ok=True)
            
            dest_path = files_dir / resource_path.name
            # Handle name conflicts
            if dest_path.exists():
                base_name = dest_path.stem
                counter = 1
                while dest_path.exists():
                    dest_path = files_dir / f"{base_name}_{counter}.html"
                    counter += 1
            
            shutil.copy2(resource_path, dest_path)
            
            # Store the destination path so parent can open it
            self.added_file_path = dest_path
            
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add resource to project:\n{e}")
    
    def _on_new_resource(self):
        """Create a new resource in the library."""
        # Show dialog to create new link
        name, ok = QInputDialog.getText(self, "New Resource", "Resource Name:")
        if not ok or not name.strip():
            return
        
        url, ok = QInputDialog.getText(self, "New Resource", "URL:")
        if not ok or not url.strip():
            return
        
        # Add protocol if missing
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Save to library resources
        try:
            filename = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name.strip())
            filename = filename.strip()
            if not filename:
                filename = "resource"
            
            # Ensure unique filename
            base_filename = filename
            counter = 1
            html_file = self.library_resources_dir / f"{filename}.html"
            while html_file.exists():
                filename = f"{base_filename}_{counter}"
                html_file = self.library_resources_dir / f"{filename}.html"
                counter += 1
            
            # Create HTML content with meta redirect
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0; url={url}">
    <title>{name.strip()}</title>
</head>
<body>
    <p>Redirecting to <a href="{url}">{name.strip()}</a>...</p>
</body>
</html>"""
            
            html_file.write_text(html_content, encoding="utf-8")
            
            # Refresh list
            self._refresh_resources_list()
            
            QMessageBox.information(self, "Success", f"Resource '{name.strip()}' added to library.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create resource:\n{e}")
    
    def _on_resource_context_menu(self, position):
        """Show context menu for resource."""
        item = self.resources_list.itemAt(position)
        if not item:
            return
        
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        
        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._on_rename_resource(item))
        
        show_location_action = menu.addAction("Show File Location")
        show_location_action.triggered.connect(lambda: self._on_show_resource_location(item))
        
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._on_delete_resource(item))
        
        menu.exec(self.resources_list.mapToGlobal(position))
    
    def _on_show_resource_location(self, item: QListWidgetItem) -> None:
        """Reveal the resource file in the system file browser."""
        resource_path = Path(item.data(Qt.ItemDataRole.UserRole))
        if not resource_path.exists():
            QMessageBox.warning(self, "Error", "Resource file not found.")
            return
        
        try:
            reveal_in_finder(resource_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to show file location:\n{e}")
    
    def eventFilter(self, obj, event):
        """Automatically switch options based on focus/click/enter key."""
        search_field = getattr(self, "search_input", None)
        url_field = getattr(self, "url_input", None)
        
        return_keys = {Qt.Key.Key_Return.value, Qt.Key.Key_Enter.value}
        
        if obj == search_field:
            if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.FocusIn):
                self._set_option(False)
            elif event.type() == QEvent.Type.KeyPress and event.key() in return_keys:
                self._set_option(False)
                self._submit_search_via_enter()
                return True
        elif obj == url_field:
            if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.FocusIn):
                self._set_option(True)
            elif event.type() == QEvent.Type.KeyPress and event.key() in return_keys:
                self._set_option(True)
                self._submit_paste_via_enter()
                return True
        return super().eventFilter(obj, event)
    
    def _on_rename_resource(self, item: QListWidgetItem):
        """Rename a resource."""
        resource_path = Path(item.data(Qt.ItemDataRole.UserRole))
        if not resource_path.exists():
            QMessageBox.warning(self, "Error", "Resource file not found.")
            return
        
        # Load current HTML
        try:
            import re
            content = resource_path.read_text(encoding="utf-8")
            current_name, url = self._parse_html_link(content, resource_path.stem)
            
            # Ask for new name
            new_name, ok = QInputDialog.getText(
                self,
                "Rename Resource",
                "New name:",
                text=current_name
            )
            
            if not ok or not new_name.strip() or new_name.strip() == current_name:
                return
            
            # Update HTML with new title (keep URL the same)
            new_content = re.sub(
                r'<title>.*?</title>',
                f'<title>{new_name.strip()}</title>',
                content,
                flags=re.IGNORECASE | re.DOTALL
            )
            
            # Also update the body text
            new_content = re.sub(
                r'<p>Redirecting to <a href="[^"]+">.*?</a>...</p>',
                f'<p>Redirecting to <a href="{url}">{new_name.strip()}</a>...</p>',
                new_content,
                flags=re.IGNORECASE | re.DOTALL
            )
            
            resource_path.write_text(new_content, encoding="utf-8")
            
            # Refresh list
            self._refresh_resources_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to rename resource:\n{e}")
    
    def _on_delete_resource(self, item: QListWidgetItem):
        """Delete a resource."""
        resource_path = Path(item.data(Qt.ItemDataRole.UserRole))
        if not resource_path.exists():
            QMessageBox.warning(self, "Error", "Resource file not found.")
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete this resource?\n\n{item.text()}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                resource_path.unlink()
                self._refresh_resources_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete resource:\n{e}")
