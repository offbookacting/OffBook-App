#!/bin/bash
# Launcher script for Off Book
# This script sets the process name so it shows as "Off Book" in the dock

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# On macOS, use Python with process name setting
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Try to set process name using exec -a (works on some systems)
    exec -a "Off Book" "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"
else
    # On other systems, just run normally
    "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"
fi

