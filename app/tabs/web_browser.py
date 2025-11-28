# app/tabs/web_browser.py
"""
Simple web browser tab with navigation controls and ad blocker.
"""
from pathlib import Path
from typing import Optional, Tuple
import json
import re

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QToolButton, QMessageBox, QMenu
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage

ICONS_DIR = Path(__file__).resolve().parents[2] / "UI" / "Icons"
ADBLOCK_ON_ICON = ICONS_DIR / "audio-description-slasg-svgrepo-com.svg"
ADBLOCK_OFF_ICON = ICONS_DIR / "audio-description-svgrepo-com.svg"

class AdBlocker:
    """Simple ad blocker using filter lists."""
    
    def __init__(self):
        self.enabled = True
        self.block_patterns = self._load_default_patterns()
    
    def _load_default_patterns(self):
        """Load default ad blocking patterns."""
        # Common ad domains and patterns
        return [
            # Ad networks
            r'.*doubleclick\.net.*',
            r'.*googleadservices\.com.*',
            r'.*googlesyndication\.com.*',
            r'.*amazon-adsystem\.com.*',
            r'.*advertising\.com.*',
            r'.*adserver\..*',
            r'.*ads\..*',
            r'.*ad\..*',
            r'.*banner\..*',
            r'.*popup\..*',
            r'.*click\..*tracker.*',
            r'.*analytics\..*',
            r'.*facebook\.com/tr.*',
            r'.*google-analytics\.com.*',
            # Common ad scripts
            r'.*/ad[sv]?\.js.*',
            r'.*/ads\..*',
            r'.*/advert.*',
            r'.*/banner.*',
            r'.*/popup.*',
        ]
    
    def should_block(self, url: str) -> bool:
        """Check if URL should be blocked."""
        if not self.enabled:
            return False
        
        url_lower = url.lower()
        for pattern in self.block_patterns:
            if re.match(pattern, url_lower):
                return True
        return False


class WebBrowser(QWidget):
    """Simple web browser with navigation and ad blocking."""
    
    open_in_new_tab = pyqtSignal(str, str)  # Signal: (url, position_after_file_path)
    
    def __init__(self, initial_url: Optional[str] = None, web_file_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.web_file_path = web_file_path
        self.ad_blocker = AdBlocker()
        self.context_menu_link_url: Optional[str] = None
        self._setup_ui()
        
        print(f"DEBUG WebBrowser.__init__ called with initial_url: '{initial_url}'")
        print(f"DEBUG WebBrowser.__init__ type of initial_url: {type(initial_url)}")
        
        if initial_url:
            self.load_url(initial_url)
        else:
            print("DEBUG: No initial_url provided, loading Google")
            self.load_url("https://www.google.com")
    
    def _setup_ui(self):
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Navigation toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        toolbar.setSpacing(5)
        
        # Back button
        self.btn_back = QToolButton()
        self.btn_back.setText("←")
        self.btn_back.setToolTip("Back")
        self.btn_back.clicked.connect(self._on_back)
        toolbar.addWidget(self.btn_back)
        
        # Forward button
        self.btn_forward = QToolButton()
        self.btn_forward.setText("→")
        self.btn_forward.setToolTip("Forward")
        self.btn_forward.clicked.connect(self._on_forward)
        toolbar.addWidget(self.btn_forward)
        
        # Refresh button
        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("⟳")
        self.btn_refresh.setToolTip("Refresh")
        self.btn_refresh.clicked.connect(self._on_refresh)
        toolbar.addWidget(self.btn_refresh)
        
        # Ad blocker toggle button
        self.btn_adblock = QToolButton()
        self.btn_adblock.setCheckable(True)
        self.btn_adblock.setChecked(True)
        self._update_adblock_icon(True)
        self.btn_adblock.setToolTip("Ad Blocker (Enabled)")
        self.btn_adblock.clicked.connect(self._on_adblock_toggled)
        self.btn_adblock.setStyleSheet("""
            QToolButton:checked {
                background-color: #4CAF50;
                color: white;
            }
        """)
        toolbar.addWidget(self.btn_adblock)
        
        # URL bar (clickable to re-search)
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search query...")
        self.url_bar.returnPressed.connect(self._on_url_entered)
        self.url_bar.installEventFilter(self)
        toolbar.addWidget(self.url_bar, stretch=1)
        
        # Go button
        btn_go = QPushButton("Go")
        btn_go.clicked.connect(self._on_url_entered)
        toolbar.addWidget(btn_go)
        
        layout.addLayout(toolbar)
        
        # Web view
        self.web_view = QWebEngineView()
        
        # Set up profile with custom request interceptor for ad blocking
        profile = QWebEngineProfile.defaultProfile()
        # Use a complete, modern user agent string for YouTube and other sites
        profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Connect URL changed signal
        self.web_view.urlChanged.connect(self._on_url_changed)
        
        # Enable context menu for the web view
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.web_view.customContextMenuRequested.connect(self._on_web_view_context_menu)
        
        # Enable settings for YouTube and modern web content
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        
        # Enable auto-loading images and other resources
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        
        layout.addWidget(self.web_view, stretch=1)
    
    def load_url(self, url: str):
        """Load a URL in the browser."""
        print(f"DEBUG WebBrowser.load_url called with: '{url}'")
        print(f"DEBUG WebBrowser.load_url type: {type(url)}")
        print(f"DEBUG WebBrowser.load_url repr: {repr(url)}")
        
        # Handle None or empty URL
        if not url:
            print("DEBUG: URL is None or empty, defaulting to Google")
            url = "https://www.google.com"
        
        qurl = QUrl(url)
        print(f"DEBUG: Initial QUrl scheme: {qurl.scheme()}")
        
        if not qurl.isValid() or not qurl.scheme():
            potential_path = Path(url)
            if potential_path.exists():
                print(f"DEBUG: Treating input as local file path: {potential_path}")
                qurl = QUrl.fromLocalFile(str(potential_path.resolve()))
            else:
                # Ensure URL has protocol
                if '.' in url and ' ' not in url:
                    print("DEBUG: Looks like URL, adding https://")
                    qurl = QUrl(f"https://{url}")
                else:
                    print("DEBUG: Treating input as search query")
                    import urllib.parse
                    encoded_query = urllib.parse.quote(url)
                    qurl = QUrl(f"https://www.google.com/search?q={encoded_query}")
        
        final_url = qurl.toString()
        print(f"DEBUG WebBrowser.load_url final QUrl: '{final_url}'")
        self.url_bar.setText(final_url)
        self.web_view.setUrl(qurl)
        
    def _on_back(self):
        """Navigate back."""
        self.web_view.back()
    
    def _on_forward(self):
        """Navigate forward."""
        self.web_view.forward()
    
    def _on_refresh(self):
        """Refresh the page."""
        self.web_view.reload()
    
    def _update_adblock_icon(self, enabled: bool) -> None:
        icon_path = ADBLOCK_ON_ICON if enabled else ADBLOCK_OFF_ICON
        if icon_path.exists():
            self.btn_adblock.setIcon(QIcon(str(icon_path)))
            self.btn_adblock.setIconSize(QSize(20, 20))
            self.btn_adblock.setText("")
        else:
            self.btn_adblock.setIcon(QIcon())
            self.btn_adblock.setText("🛡")
    
    def _on_adblock_toggled(self, checked: bool):
        """Toggle ad blocker."""
        self.ad_blocker.enabled = checked
        self._update_adblock_icon(checked)
        
        if checked:
            self.btn_adblock.setToolTip("Ad Blocker (Enabled)")
            QMessageBox.information(
                self,
                "Ad Blocker",
                "Ad blocker enabled. Refresh the page to see changes."
            )
        else:
            self.btn_adblock.setToolTip("Ad Blocker (Disabled)")
            QMessageBox.information(
                self,
                "Ad Blocker",
                "Ad blocker disabled. Refresh the page to see changes."
            )
    
    def _on_url_entered(self):
        """Handle URL entry or search."""
        text = self.url_bar.text().strip()
        if text:
            self.load_url(text)
    
    def _on_url_changed(self, url: QUrl):
        """Handle URL change (navigation)."""
        # Update URL bar with current URL
        current_url = url.toString()
        self.url_bar.setText(current_url)
        
        # Update the .web file with the new URL if we have a web_file_path
        if self.web_file_path and self.web_file_path.exists():
            self._update_web_file(current_url)
        
        # Apply ad blocking
        if self.ad_blocker.should_block(current_url):
            # Block the request by loading empty page
            # Note: Full ad blocking requires request interception which is complex
            # This is a basic implementation
            pass
    
    def _update_web_file(self, new_url: str):
        """Update the HTML file with the new URL."""
        suffix = self.web_file_path.suffix.lower()
        try:
            if suffix == '.web':
                data = json.loads(self.web_file_path.read_text(encoding="utf-8"))
                data["url"] = new_url
                self.web_file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                print(f"Updated WEB file with new URL: {new_url}")
                return
            if suffix in ('.html', '.htm'):
                import re
                content = self.web_file_path.read_text(encoding="utf-8")
                if 'meta http-equiv="refresh"' not in content.lower():
                    return
                
                new_content = re.sub(
                    r'content="0;\s*url=[^"]+"',
                    f'content="0; url={new_url}"',
                    content,
                    flags=re.IGNORECASE
                )
                
                title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else "Link"
                
                new_content = re.sub(
                    r'<p>Redirecting to <a href="[^"]+">.*?</a>...</p>',
                    f'<p>Redirecting to <a href="{new_url}">{title}</a>...</p>',
                    new_content,
                    flags=re.IGNORECASE | re.DOTALL
                )
                
                self.web_file_path.write_text(new_content, encoding="utf-8")
                print(f"Updated HTML file with new URL: {new_url}")
        except Exception as e:
            print(f"Error updating web file: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_web_view_context_menu(self, position):
        """Show custom context menu for web view."""
        # Get the context menu data from the page
        menu = QMenu(self)
        
        # Add "Open in New Tab" action
        act_new_tab = menu.addAction("Open in New Tab")
        act_new_tab.triggered.connect(self._on_open_in_new_tab)
        
        # Get the link URL under cursor using JavaScript
        self.web_view.page().runJavaScript(
            """
            (function() {
                var element = document.elementFromPoint(%d, %d);
                if (element && element.tagName === 'A') {
                    return element.href;
                }
                // Check parent elements
                while (element && element.tagName !== 'A') {
                    element = element.parentElement;
                }
                return element ? element.href : null;
            })();
            """ % (position.x(), position.y()),
            self._handle_link_url
        )
        
        menu.exec(self.web_view.mapToGlobal(position))
    
    def _handle_link_url(self, url):
        """Store the link URL for opening in new tab."""
        self.context_menu_link_url = url
        print(f"DEBUG: Context menu link URL: {url}")
    
    def _on_open_in_new_tab(self):
        """Open the link in a new tab (create new .web file)."""
        if not self.context_menu_link_url:
            # No link was found, use current page URL
            url = self.web_view.url().toString()
        else:
            url = self.context_menu_link_url
        
        if not url:
            QMessageBox.warning(self, "No Link", "No link found at that position.")
            return
        
        # Emit signal to create new web file
        # The signal includes the URL and the current file path (to position the new file after it)
        current_file_path = str(self.web_file_path) if self.web_file_path else ""
        self.open_in_new_tab.emit(url, current_file_path)
        
        # Clear the stored link URL
        self.context_menu_link_url = None

    @classmethod
    def load_web_file(cls, web_file_path: Path) -> Optional[str]:
        """Load URL from a web file for external popout windows."""
        _, url = cls.parse_web_metadata(web_file_path)
        return url

    @staticmethod
    def parse_web_metadata(web_file_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """Extract (name, url) metadata from supported web link file formats."""
        suffix = web_file_path.suffix.lower()
        try:
            if suffix == '.web':
                data = json.loads(web_file_path.read_text(encoding="utf-8"))
                name = data.get("name") or web_file_path.stem
                url = data.get("url")
                if isinstance(name, str):
                    name = name.strip() or web_file_path.stem
                else:
                    name = web_file_path.stem
                if isinstance(url, str):
                    url = url.strip() or None
                else:
                    url = None
                return name, url
            if suffix in ('.html', '.htm'):
                content = web_file_path.read_text(encoding="utf-8", errors="ignore")
                title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                name = title_match.group(1).strip() if title_match else web_file_path.stem
                url_match = re.search(r'content="0;\s*url=([^"]+)"', content, re.IGNORECASE)
                url = url_match.group(1).strip() if url_match else None
                return name, url
        except Exception as exc:
            print(f"Warning: failed to parse web metadata for {web_file_path}: {exc}")
        return web_file_path.stem, None
