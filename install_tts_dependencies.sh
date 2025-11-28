#!/bin/bash
# Helper script to install TTS dependencies (piper-phonemize)
# This script checks for Rust and installs piper-phonemize if possible

set -e

echo "Scene Partner - TTS Dependencies Installer"
echo "=========================================="
echo ""

# Check if Rust is installed
if command -v rustc &> /dev/null; then
    echo "✓ Rust is installed: $(rustc --version)"
else
    echo "✗ Rust is not installed"
    echo ""
    echo "Rust is required to build piper-phonemize."
    echo ""
    read -p "Would you like to install Rust now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing Rust..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
        echo ""
        echo "Rust installation complete!"
        echo "Please restart your terminal or run: source ~/.cargo/env"
        echo "Then run this script again to install piper-phonemize."
        exit 0
    else
        echo "Rust installation cancelled."
        echo "You can install Rust manually later with:"
        echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        exit 1
    fi
fi

# Check if cargo is in PATH (might need to source cargo env)
if ! command -v cargo &> /dev/null; then
    echo "⚠ Cargo not found in PATH. Trying to source ~/.cargo/env..."
    if [ -f ~/.cargo/env ]; then
        source ~/.cargo/env
        if ! command -v cargo &> /dev/null; then
            echo "✗ Cargo still not found after sourcing ~/.cargo/env"
            echo "Please restart your terminal and try again."
            exit 1
        fi
    else
        echo "✗ Cargo not found and ~/.cargo/env doesn't exist"
        echo "Please restart your terminal after installing Rust."
        exit 1
    fi
fi

echo "✓ Cargo is available: $(cargo --version)"
echo ""

# Check if piper-phonemize is already installed
if python3 -c "import piper_phonemize" 2>/dev/null; then
    echo "✓ piper-phonemize is already installed"
    echo ""
    read -p "Would you like to reinstall it? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    echo "Reinstalling piper-phonemize..."
else
    echo "Installing piper-phonemize..."
fi

# Install piper-phonemize
if pip3 install piper-phonemize; then
    echo ""
    echo "✓ piper-phonemize installed successfully!"
    echo ""
    echo "TTS features should now work in Scene Partner."
    echo "You may need to restart the application."
else
    echo ""
    echo "✗ Failed to install piper-phonemize"
    echo ""
    echo "You can try installing from source:"
    echo "  pip3 install git+https://github.com/rhasspy/piper-phonemize.git"
    exit 1
fi

