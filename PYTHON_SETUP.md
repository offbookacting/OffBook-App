# Python Environment Setup

## Current Setup

A virtual environment has been created using Python 3.9.6 (compatible with all dependencies).

## Running the App

### Option 1: Use the run script (easiest)
```bash
./run.sh
```

### Option 2: Manual activation
```bash
source .venv/bin/activate
python main.py
```

## TTS Features (Optional)

The app will run without TTS features, but if you want to enable them, you need to install `piper-phonemize`:

### Installing piper-phonemize

1. **Install Rust** (required to build piper-phonemize):
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source $HOME/.cargo/env
   ```

2. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

3. **Install piper-phonemize**:
   ```bash
   pip install piper-phonemize
   ```

   Or from source:
   ```bash
   pip install git+https://github.com/rhasspy/piper-phonemize.git
   ```

## What's Installed

✅ PyQt6 (GUI framework)
✅ PyMuPDF (PDF parsing)
✅ pypdf (PDF parsing)
✅ Pillow (Image processing)
✅ pytesseract (OCR - optional)
✅ spacy (NLP - optional)
✅ requests (HTTP requests)
✅ numpy (Numerical computing)
✅ onnxruntime (TTS engine)
✅ piper-tts (TTS package)

⚠️ piper-phonemize (TTS dependency - requires Rust to build)

## Notes

- The app uses Python 3.9.6 from `/usr/bin/python3`
- All dependencies are installed in the `.venv` virtual environment
- TTS features will show an error message if used without piper-phonemize, but all other features work normally

