#!/usr/bin/env python3
"""
Cross-platform launcher for Off Book / Scene Partner
Works on macOS, Windows, and Linux
"""
import sys
import os
from pathlib import Path

def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()
    os.chdir(script_dir)
    
    # Determine Python executable path
    venv_python = script_dir / ".venv" / "bin" / "python"
    if sys.platform == "win32":
        venv_python = script_dir / ".venv" / "Scripts" / "python.exe"
    
    # Use venv Python if it exists, otherwise use system Python
    if venv_python.exists():
        python_exe = str(venv_python)
    else:
        python_exe = sys.executable
    
    # Path to main.py
    main_py = script_dir / "main.py"
    
    if not main_py.exists():
        print(f"Error: main.py not found at {main_py}")
        sys.exit(1)
    
    # On macOS, try to set process name (optional, may not work on all systems)
    if sys.platform == "darwin":
        try:
            # Try to set process name using exec -a (works on some systems)
            os.execv(python_exe, [python_exe, str(main_py)] + sys.argv[1:])
        except Exception:
            # Fallback to subprocess if execv fails
            import subprocess
            subprocess.run([python_exe, str(main_py)] + sys.argv[1:])
    else:
        # On other platforms, just run normally
        import subprocess
        subprocess.run([python_exe, str(main_py)] + sys.argv[1:])

if __name__ == "__main__":
    main()

