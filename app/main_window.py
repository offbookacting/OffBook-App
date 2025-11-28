# app/main_window.py
"""
Main application window that manages project browser and workspace.
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

# Add project root to Python path to ensure imports work when running directly
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QFileDialog, QMessageBox, QDialog

from core.project_manager import ProjectManager, Project
from app.project_browser import ProjectBrowser
from app.workspace import WorkspaceWindow


class MainApplicationWindow(QMainWindow):
    """
    Main window that switches between project browser and workspace.
    Starts with project browser, opens workspace when project is selected.
    """
    
    def __init__(self):
        super().__init__()
        try:
            self.pm = ProjectManager(app_name="ActorRehearsal")
            self.current_workspace: Optional[WorkspaceWindow] = None
            
            self.setWindowTitle("Scene Partner")
            self.resize(1200, 800)
            
            # Stacked widget to switch between browser and workspace
            self.stacked = QStackedWidget()
            self.setCentralWidget(self.stacked)
            
            # Project browser
            try:
                self.browser = ProjectBrowser(self.pm)
                self.browser.project_selected.connect(self._on_project_selected)
                self.browser.project_created.connect(self._on_project_selected)
                self.browser.library_required.connect(self._on_library_required)
                self.stacked.addWidget(self.browser)
                
                # Show browser initially
                self.stacked.setCurrentWidget(self.browser)
                
                # Prompt for library folder if not set, otherwise refresh projects
                if not self.pm.config.library_path:
                    # Don't block on library prompt - let user use the button
                    pass
                else:
                    # Refresh projects on app open
                    try:
                        self.browser._refresh_projects()
                    except Exception as e:
                        print(f"Warning: Could not refresh projects: {e}")
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to initialize project browser:\n{e}"
                )
                raise
        except Exception as e:
            QMessageBox.critical(
                None,
                "Error",
                f"Failed to initialize main window:\n{e}"
            )
            raise
    
    def _on_project_selected(self, project_id: int) -> None:
        """Handle project selection - open workspace."""
        try:
            project = self.pm.get(project_id)
            workspace = WorkspaceWindow(self.pm, project)
            workspace.closed.connect(self._on_workspace_closed)
            
            # Add workspace to stack
            self.stacked.addWidget(workspace)
            self.stacked.setCurrentWidget(workspace)
            self.current_workspace = workspace
            
            # Update window title
            self.setWindowTitle(f"Scene Partner - {project.name}")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to open project: {e}")
    
    def _on_workspace_closed(self) -> None:
        """Handle workspace close - return to browser."""
        if self.current_workspace:
            self.stacked.removeWidget(self.current_workspace)
            self.current_workspace = None
        
        self.stacked.setCurrentWidget(self.browser)
        self.setWindowTitle("Scene Partner")
    
    def _prompt_for_library(self) -> None:
        """Prompt user to create a library folder on startup."""
        from app.library_creation_dialog import LibraryCreationDialog
        from PyQt6.QtWidgets import QMessageBox
        
        dialog = LibraryCreationDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.library_path:
                try:
                    # Set library and scan for projects
                    self.pm.set_library(str(dialog.library_path))
                    
                    # Check if voices need to be installed
                    if self.pm.library and self.pm.library.needs_voice_installation():
                        from app.voice_install_dialog import VoiceInstallDialog
                        models_dir, presets_dir = self.pm.library.get_voice_directories()
                        install_dialog = VoiceInstallDialog(models_dir, presets_dir, self)
                        install_dialog.exec()
                        # Clear the flag
                        self.pm.library._voices_need_installation = False
                    
                    self.browser._refresh_projects()
                    self.browser.lbl_library.setText(f"Library: {dialog.library_path.name}")
                    self.browser.btn_new.setEnabled(True)
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to set library folder:\n{e}"
                    )
        else:
            # User cancelled - show message
            QMessageBox.information(
                self,
                "Library Required",
                "Scene Partner requires a library to work.\n\n"
                "You can create a library later using the 'Choose Library' button."
            )
    
    def _on_library_required(self) -> None:
        """Handle library requirement signal from browser."""
        self._prompt_for_library()
    
    def closeEvent(self, event) -> None:
        """Handle application close."""
        # Clean up workspace if open
        if self.current_workspace:
            self.current_workspace.close()
        super().closeEvent(event)


def run() -> None:
    """Run the application."""
    app = QApplication(sys.argv)
    
    try:
        # Check Python version and warn if 3.14+ (but don't block startup)
        if sys.version_info >= (3, 14):
            # Show warning but allow app to continue
            QMessageBox.information(
                None,
                "Python Version Notice",
                "You are using Python 3.14.\n\n"
                "Note: TTS features may not work until 'onnxruntime' and 'piper-phonemize' "
                "support Python 3.14.\n\n"
                "All other features should work normally."
            )
        
        # Load stylesheet if present
        qss_path = Path(__file__).resolve().parent.parent / "UI" / "styles.qss"
        if qss_path.exists():
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    app.setStyleSheet(f.read())
            except Exception as e:
                print(f"Warning: Could not load stylesheet: {e}")
        
        # Set application icon (appears in dock and all windows)
        icons_dir = Path(__file__).resolve().parent.parent / "UI" / "Icons"
        if icons_dir.exists():
            icon_path = icons_dir / "app_icon.png"
            if icon_path.exists():
                try:
                    app_icon = QIcon(str(icon_path))
                    app.setWindowIcon(app_icon)  # Sets icon for all windows and dock
                except Exception:
                    pass  # Icon loading is optional
        
        # Create and show main window
        try:
            win = MainApplicationWindow()
        except Exception as e:
            QMessageBox.critical(
                None,
                "Error Starting Application",
                f"Failed to create main window:\n\n{e}\n\n"
                "Please check the console for more details."
            )
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        win.show()
        win.raise_()  # Bring window to front
        win.activateWindow()  # Activate the window
        sys.exit(app.exec())
    except Exception as e:
        QMessageBox.critical(
            None,
            "Fatal Error",
            f"Application failed to start:\n\n{e}\n\n"
            "Please check the console for more details."
        )
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()

