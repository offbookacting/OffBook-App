#!/usr/bin/env python3
"""
Helper script to install TTS dependencies (piper-phonemize).
This script checks for Rust and installs piper-phonemize if possible.
"""
import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, check=True, shell=False):
    """Run a command and return success status."""
    try:
        if isinstance(cmd, str) and shell:
            result = subprocess.run(cmd, shell=True, check=check, 
                                  capture_output=True, text=True)
        else:
            result = subprocess.run(cmd, check=check, 
                                  capture_output=True, text=True)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stdout.strip() if e.stdout else "", e.stderr.strip() if e.stderr else ""
    except Exception as e:
        return False, "", str(e)


def check_rust_installed():
    """Check if Rust is installed."""
    success, stdout, _ = run_command(["rustc", "--version"], check=False)
    if success:
        return True, stdout
    return False, None


def check_cargo_available():
    """Check if cargo is available."""
    success, stdout, _ = run_command(["cargo", "--version"], check=False)
    if success:
        return True, stdout
    return False, None


def check_espeak_ng_available():
    """Check if espeak-ng development headers are available."""
    # Try to find espeak-ng headers
    if sys.platform == "darwin":  # macOS
        # Check common Homebrew locations
        brew_prefix = None
        success, stdout, _ = run_command(["brew", "--prefix"], check=False)
        if success:
            brew_prefix = stdout.strip()
        
        if brew_prefix:
            header_path = Path(brew_prefix) / "include" / "espeak-ng" / "speak_lib.h"
            if header_path.exists():
                return True, str(header_path)
        
        # Check if espeak-ng is installed via Homebrew
        success, _, _ = run_command(["brew", "list", "espeak-ng"], check=False)
        if success:
            return True, "espeak-ng installed via Homebrew"
        
        return False, None
    elif sys.platform.startswith("linux"):
        # On Linux, check common locations
        common_paths = [
            "/usr/include/espeak-ng/speak_lib.h",
            "/usr/local/include/espeak-ng/speak_lib.h",
        ]
        for path in common_paths:
            if Path(path).exists():
                return True, path
        return False, None
    else:
        # Windows - espeak-ng might be bundled or need manual installation
        return None, None  # Unknown


def check_piper_phonemize_installed():
    """Check if piper-phonemize is already installed."""
    try:
        import piper_phonemize
        return True
    except ImportError:
        return False


def install_rust():
    """Install Rust using rustup."""
    print("\nInstalling Rust...")
    print("This will download and run the Rust installer.")
    print("You may be prompted for confirmation.\n")
    
    # Download and run rustup installer
    if sys.platform == "win32":
        # Windows
        url = "https://win.rustup.rs/x86_64"
        print("For Windows, please visit: https://rustup.rs/")
        print("Or download and run: https://win.rustup.rs/x86_64")
        return False
    else:
        # Unix-like (macOS, Linux)
        success, stdout, stderr = run_command(
            "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
            shell=True
        )
        if success:
            print("✓ Rust installation initiated!")
            print("\nPlease restart your terminal or run:")
            print("  source ~/.cargo/env")
            print("\nThen run this script again to install piper-phonemize.")
            return True
        else:
            print(f"✗ Failed to install Rust: {stderr}")
            return False


def install_piper_phonemize():
    """Install piper-phonemize using pip."""
    print("Installing piper-phonemize...")
    
    # Try regular install first
    success, stdout, stderr = run_command(
        [sys.executable, "-m", "pip", "install", "piper-phonemize"],
        check=False
    )
    
    if success:
        print("✓ piper-phonemize installed successfully!")
        return True
    else:
        print("✗ Regular installation failed. Trying from source...")
        # Try installing from source
        success, stdout, stderr = run_command(
            [sys.executable, "-m", "pip", "install", 
             "git+https://github.com/rhasspy/piper-phonemize.git"],
            check=False
        )
        if success:
            print("✓ piper-phonemize installed successfully from source!")
            return True
        else:
            print(f"✗ Installation failed: {stderr}")
            return False


def main():
    """Main installation flow."""
    print("Scene Partner - TTS Dependencies Installer")
    print("=" * 40)
    print()
    
    # Check if piper-phonemize is already installed
    if check_piper_phonemize_installed():
        print("✓ piper-phonemize is already installed")
        response = input("\nWould you like to reinstall it? (y/n): ").strip().lower()
        if response != 'y':
            print("Installation cancelled.")
            return 0
        print("Reinstalling piper-phonemize...")
    else:
        # Check for Rust
        rust_installed, rust_version = check_rust_installed()
        if rust_installed:
            print(f"✓ Rust is installed: {rust_version}")
        else:
            print("✗ Rust is not installed")
            print("\nRust is required to build piper-phonemize.")
            response = input("\nWould you like to install Rust now? (y/n): ").strip().lower()
            if response == 'y':
                if install_rust():
                    return 0
                else:
                    print("\nYou can install Rust manually later:")
                    print("  Visit: https://rustup.rs/")
                    print("  Or run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
                    return 1
            else:
                print("\nRust installation cancelled.")
                print("You can install Rust manually later:")
                print("  Visit: https://rustup.rs/")
                print("  Or run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
                return 1
        
        # Check for cargo
        cargo_available, cargo_version = check_cargo_available()
        if cargo_available:
            print(f"✓ Cargo is available: {cargo_version}")
        else:
            print("⚠ Cargo not found in PATH")
            # Try to source cargo env if on Unix-like
            if sys.platform != "win32":
                cargo_env = Path.home() / ".cargo" / "env"
                if cargo_env.exists():
                    print("Found ~/.cargo/env. Please restart your terminal or run:")
                    print("  source ~/.cargo/env")
                    print("Then run this script again.")
                    return 1
            print("Please restart your terminal after installing Rust.")
            return 1
        
        # Check for espeak-ng
        espeak_status, espeak_info = check_espeak_ng_available()
        if espeak_status is True:
            print(f"✓ espeak-ng development headers found: {espeak_info}")
        elif espeak_status is False:
            print("✗ espeak-ng development headers not found")
            print("\nespeak-ng is required to build piper-phonemize.")
            if sys.platform == "darwin":  # macOS
                print("\nOn macOS, install espeak-ng using Homebrew:")
                print("  1. Install Homebrew (if not installed):")
                print("     /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                print("  2. Install espeak-ng:")
                print("     brew install espeak-ng")
                print("\nThen run this script again.")
            elif sys.platform.startswith("linux"):
                print("\nOn Linux, install espeak-ng development package:")
                print("  Ubuntu/Debian: sudo apt-get install libespeak-ng-dev")
                print("  Fedora/RHEL: sudo dnf install espeak-ng-devel")
                print("  Arch: sudo pacman -S espeak-ng")
                print("\nThen run this script again.")
            else:
                print("\nPlease install espeak-ng development headers for your platform.")
                print("See: https://github.com/espeak-ng/espeak-ng")
            return 1
        # If espeak_status is None, we're on Windows or unknown platform - continue anyway
    
    print()
    
    # Install piper-phonemize
    if install_piper_phonemize():
        print("\n" + "=" * 40)
        print("✓ Installation complete!")
        print("\nTTS features should now work in Scene Partner.")
        print("You may need to restart the application.")
        return 0
    else:
        print("\n" + "=" * 40)
        print("✗ Installation failed")
        print("\nCommon issues:")
        print("1. Missing espeak-ng development headers")
        if sys.platform == "darwin":
            print("   Install with: brew install espeak-ng")
        elif sys.platform.startswith("linux"):
            print("   Install with: sudo apt-get install libespeak-ng-dev (Ubuntu/Debian)")
        print("2. Missing Rust/Cargo")
        print("   Install with: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
        print("\nYou can try installing manually:")
        print("  pip install piper-phonemize")
        print("  or")
        print("  pip install git+https://github.com/rhasspy/piper-phonemize.git")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

