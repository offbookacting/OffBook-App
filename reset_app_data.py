#!/usr/bin/env python3
"""
Reset Scene Partner application data.

This script can reset:
1. Application configuration (config.json, ui_config.json)
2. Library data (database, voice presets, models)
3. All data (complete reset)
"""
from __future__ import annotations
import sys
import shutil
from pathlib import Path
from typing import Optional

# Get app support directory
def get_app_support_dir() -> Path:
    """Get the application support directory."""
    return Path.home() / "Library" / "Application Support" / "ActorRehearsal"


def reset_app_config() -> None:
    """Reset application configuration files."""
    app_dir = get_app_support_dir()
    
    files_to_remove = [
        "config.json",
        "ui_config.json",
    ]
    
    removed = []
    for filename in files_to_remove:
        file_path = app_dir / filename
        if file_path.exists():
            file_path.unlink()
            removed.append(filename)
    
    if removed:
        print(f"✓ Removed application config files: {', '.join(removed)}")
    else:
        print("✓ No application config files found to remove")


def reset_library_data(library_path: Optional[str] = None) -> None:
    """Reset library data (database, voice presets, models)."""
    if not library_path:
        # Try to read from config if it exists
        app_dir = get_app_support_dir()
        config_path = app_dir / "config.json"
        if config_path.exists():
            import json
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                library_path = data.get("library_path")
            except Exception:
                pass
    
    if not library_path:
        print("⚠ No library path found. Skipping library data reset.")
        print("  (You can specify a library path as an argument)")
        return
    
    library_root = Path(library_path).expanduser().resolve()
    if not library_root.exists():
        print(f"⚠ Library path does not exist: {library_root}")
        return
    
    # Reset database
    db_dir = library_root / ".rehearsal"
    if db_dir.exists():
        db_file = db_dir / "projects.db"
        if db_file.exists():
            db_file.unlink()
            print(f"✓ Removed database: {db_file}")
        
        # Remove attachments
        attach_dir = db_dir / "attachments"
        if attach_dir.exists():
            shutil.rmtree(attach_dir)
            print(f"✓ Removed attachments directory: {attach_dir}")
    
    # Reset voice presets and models
    customizations_dir = library_root / "customizations"
    if customizations_dir.exists():
        voice_presets_dir = customizations_dir / "voice_presets"
        if voice_presets_dir.exists():
            shutil.rmtree(voice_presets_dir)
            print(f"✓ Removed voice presets: {voice_presets_dir}")
        
        models_dir = customizations_dir / "models"
        if models_dir.exists():
            shutil.rmtree(models_dir)
            print(f"✓ Removed voice models: {models_dir}")
    
    print(f"✓ Library data reset complete for: {library_root}")


def reset_all(library_path: Optional[str] = None) -> None:
    """Reset all application data."""
    print("Resetting all application data...")
    print()
    
    reset_app_config()
    print()
    reset_library_data(library_path)
    print()
    print("✓ Complete reset finished!")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Reset Scene Partner application data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reset only application configuration
  python reset_app_data.py --config
  
  # Reset only library data (requires library path)
  python reset_app_data.py --library /path/to/library
  
  # Reset everything
  python reset_app_data.py --all
  
  # Reset everything with specific library path
  python reset_app_data.py --all --library /path/to/library
        """
    )
    
    parser.add_argument(
        "--config",
        action="store_true",
        help="Reset application configuration files only"
    )
    parser.add_argument(
        "--library",
        action="store_true",
        help="Reset library data only (database, voice presets, models)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Reset all application data"
    )
    parser.add_argument(
        "library_path",
        nargs="?",
        help="Path to library directory (optional, will try to read from config)"
    )
    
    args = parser.parse_args()
    
    # If no flags specified, show help
    if not (args.config or args.library or args.all):
        parser.print_help()
        print()
        print("⚠ No action specified. Use --config, --library, or --all")
        sys.exit(1)
    
    # Execute requested actions
    if args.all:
        reset_all(args.library_path)
    elif args.config:
        reset_app_config()
    elif args.library:
        reset_library_data(args.library_path)


if __name__ == "__main__":
    main()

