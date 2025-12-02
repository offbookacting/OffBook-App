# Size Optimization Guide

## Current Size Breakdown
- **Total Project**: ~1.8GB
- **`.venv`** (virtual environment): 858MB - ✅ Already gitignored
- **`dist/`** (built executables): 188MB - ✅ Already gitignored  
- **`build/`** (build artifacts): 111MB - ✅ Already gitignored
- **`__pycache__`**: Now cleaned and gitignored

## Quick Fixes Applied ✅

1. **Updated `.gitignore`** to exclude:
   - Python cache files (`__pycache__/`, `*.pyc`)
   - Build artifacts
   - IDE files
   - OS files

2. **Cleaned up cache files** - Removed all `__pycache__` directories

## Reducing Executable Size (Optional)

Your current executable is **95MB**, which is reasonable for a PyQt6 app. If you want to reduce it further:

### Option 1: Create a PyInstaller Spec File

Create `scene_partner.spec` to exclude unnecessary modules:

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('UI', 'UI'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'setuptools',
        'distutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Scene Partner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Enable UPX compression (if installed)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='Scene Partner.app',
    icon=None,
    bundle_identifier='com.scenepartner.app',
)
```

Then build with:
```bash
pyinstaller scene_partner.spec
```

### Option 2: Use UPX Compression

Install UPX and enable it in the spec file (see above):
```bash
brew install upx  # macOS
```

### Option 3: Exclude Unused Dependencies

Review your `requirements.txt` and remove any dependencies you don't actually use.

## Clean Up Commands

### Remove build artifacts (safe to delete):
```bash
rm -rf build/ dist/
```

### Remove virtual environment (you can recreate it):
```bash
rm -rf .venv/
```

### Clean Python cache:
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete
```

## Git Cleanup

If you've already committed large files, clean them from git history:

```bash
# Remove files from git cache (but keep locally)
git rm -r --cached build/ dist/ __pycache__/

# Commit the changes
git commit -m "Remove build artifacts and cache from git"
```

## Recommended Workflow

1. **Development**: Keep `.venv/` locally (it's gitignored)
2. **Building**: Build in `dist/` (gitignored)
3. **Distribution**: Only distribute the final `.app` file
4. **Git**: Only commit source code, not build artifacts

## Size Comparison

- **Source code only**: ~2-5MB (what should be in git)
- **With virtual environment**: ~860MB (local development only)
- **With build artifacts**: ~1.8GB (current state)
- **Final executable**: ~95MB (distribution)

The key is keeping only source code in git, and everything else locally or in CI/CD.

