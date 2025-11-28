#!/usr/bin/env python3
"""Test script to verify the app can start."""
import sys
from PyQt6.QtWidgets import QApplication
from app.main_window import MainApplicationWindow

print("Creating QApplication...")
app = QApplication(sys.argv)
print("QApplication created")

print("Creating MainApplicationWindow...")
try:
    win = MainApplicationWindow()
    print("MainApplicationWindow created successfully")
except Exception as e:
    print(f"ERROR: Failed to create window: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Showing window...")
win.show()
win.raise_()
win.activateWindow()
print("Window shown. App should be visible now.")
print("Press Ctrl+C to exit, or close the window.")

sys.exit(app.exec())

