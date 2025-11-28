# Installation Guide

## Python Version Requirements

**Important**: This application requires Python 3.9-3.13. Python 3.14 is not yet supported due to missing dependencies.

### Why Python 3.14 isn't supported yet

The `piper-tts` package depends on:
- `onnxruntime` - Not yet available for Python 3.14
- `piper-phonemize` - Not yet available for Python 3.14

These packages will need to be updated by their maintainers to support Python 3.14.

## Installation Steps

1. **Create a virtual environment** (recommended):
   ```bash
   python3.13 -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate  # On Windows
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python main.py
   ```

## Troubleshooting

### If you see "onnxruntime not available" error:

- **Option 1 (Recommended)**: Use Python 3.13 or earlier
- **Option 2**: Wait for onnxruntime to support Python 3.14
- **Option 3**: Try building from source (advanced):
  ```bash
  pip install onnxruntime --no-binary onnxruntime
  ```

### If you see "piper-phonemize not available" error:

**Easy Installation (Recommended for macOS)**:
- **macOS**: Install the pre-built wheel package (no build required):
  ```bash
  pip install piper-phonemize-cross
  ```
  This package includes pre-built wheels for macOS and avoids build issues.

**Alternative: Build from Source**:

The `piper-phonemize` package can be built from source, but requires:
- **Rust** (and Cargo)
- **espeak-ng development headers**

1. **Install espeak-ng** (required for development headers):
   - **macOS** (using Homebrew):
     ```bash
     # Install Homebrew if not already installed:
     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
     
     # Install espeak-ng:
     brew install espeak-ng
     ```
   - **Linux**:
     ```bash
     # Ubuntu/Debian:
     sudo apt-get install libespeak-ng-dev
     
     # Fedora/RHEL:
     sudo dnf install espeak-ng-devel
     
     # Arch Linux:
     sudo pacman -S espeak-ng
     ```

2. **Install Rust** (if not already installed):
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
   Then restart your terminal or run: `source ~/.cargo/env`

3. **Install piper-phonemize from source**:
   ```bash
   pip install git+https://github.com/rhasspy/piper-phonemize.git
   ```

**Note**: If you're using Python 3.14, you'll need to use Python 3.13 or earlier until `piper-phonemize` supports Python 3.14.

## Voice Installation

When you create a library for the first time, the application will automatically download all available voice presets. This happens in the background and may take a few minutes.

Voices are downloaded to: `[Library]/customizations/models/`
Presets are saved to: `[Library]/customizations/voice_presets/`

