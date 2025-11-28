# core/voice_installer.py
"""
Automatic voice installer - downloads all available voices when library is created.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, List
import json
import subprocess
import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class VoiceInstaller:
    """Automatically install default voices."""
    
    HUGGINGFACE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    
    @staticmethod
    def _discover_all_voices() -> List[Dict]:
        """
        Discover all available voices using piper.download_voices module.
        Falls back to a comprehensive list if the module is not available.
        """
        try:
            # Try to use piper.download_voices to get the list
            result = subprocess.run(
                [sys.executable, '-m', 'piper.download_voices'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                voices = []
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # Parse voice name like "en_US-amy-low"
                    parts = line.split('-')
                    if len(parts) >= 3:
                        region = parts[0]
                        voice = parts[1]
                        quality = parts[2]
                        # Extract language from region (e.g., en_US -> en)
                        lang = region.split('_')[0] if '_' in region else region[:2]
                        voices.append({
                            "language": lang,
                            "region": region,
                            "voice": voice,
                            "quality": quality
                        })
                if voices:
                    return voices
        except Exception:
            pass
        
        # Fallback: comprehensive list of common English voices
        return [
            # Amy voices
            {"language": "en", "region": "en_US", "voice": "amy", "quality": "low"},
            {"language": "en", "region": "en_US", "voice": "amy", "quality": "medium"},
            {"language": "en", "region": "en_US", "voice": "amy", "quality": "high"},
            # Lessac voices
            {"language": "en", "region": "en_US", "voice": "lessac", "quality": "low"},
            {"language": "en", "region": "en_US", "voice": "lessac", "quality": "medium"},
            {"language": "en", "region": "en_US", "voice": "lessac", "quality": "high"},
            # LibriTTS voices
            {"language": "en", "region": "en_US", "voice": "libritts", "quality": "low"},
            {"language": "en", "region": "en_US", "voice": "libritts", "quality": "medium"},
            {"language": "en", "region": "en_US", "voice": "libritts", "quality": "high"},
            # Nancy voices
            {"language": "en", "region": "en_US", "voice": "nancy", "quality": "low"},
            {"language": "en", "region": "en_US", "voice": "nancy", "quality": "medium"},
            {"language": "en", "region": "en_US", "voice": "nancy", "quality": "high"},
            # Radio voices
            {"language": "en", "region": "en_US", "voice": "radio", "quality": "low"},
            {"language": "en", "region": "en_US", "voice": "radio", "quality": "medium"},
            {"language": "en", "region": "en_US", "voice": "radio", "quality": "high"},
        ]
    
    # Cache for discovered voices
    _cached_voices: Optional[List[Dict]] = None
    
    @classmethod
    def get_all_voices(cls) -> List[Dict]:
        """Get all available voices (cached)."""
        if cls._cached_voices is None:
            cls._cached_voices = cls._discover_all_voices()
        return cls._cached_voices
    
    @staticmethod
    def _get_voice_urls(voice_info: Dict) -> Dict[str, str]:
        """Get download URLs for a voice."""
        lang = voice_info["language"]
        region = voice_info["region"]
        voice = voice_info["voice"]
        quality = voice_info["quality"]
        
        base_name = f"{region}-{voice}-{quality}"
        onnx_file = f"{base_name}.onnx"
        json_file = f"{base_name}.onnx.json"
        
        onnx_url = f"{VoiceInstaller.HUGGINGFACE_BASE}/{lang}/{region}/{voice}/{quality}/{onnx_file}"
        json_url = f"{VoiceInstaller.HUGGINGFACE_BASE}/{lang}/{region}/{voice}/{quality}/{json_file}"
        
        return {
            onnx_file: onnx_url,
            json_file: json_url
        }
    
    @staticmethod
    def download_voice_file(url: str, file_path: Path) -> bool:
        """Download a single file."""
        try:
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            response = session.get(url, stream=True, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def install_default_voices(models_dir: Path, presets_dir: Path, progress_callback=None) -> int:
        """
        Install default voices automatically.
        
        Args:
            models_dir: Directory to download .onnx files to
            presets_dir: Directory to create .onnx.json preset files in
            progress_callback: Optional callback(voice_name, current, total) for progress updates
        
        Returns:
            Number of voices successfully installed
        """
        models_dir.mkdir(parents=True, exist_ok=True)
        presets_dir.mkdir(parents=True, exist_ok=True)
        
        # Get all available voices
        all_voices = VoiceInstaller.get_all_voices()
        installed_count = 0
        total = len(all_voices)
        
        for i, voice_info in enumerate(all_voices):
            voice_name = f"{voice_info['region']}-{voice_info['voice']}-{voice_info['quality']}"
            
            if progress_callback:
                progress_callback(voice_name, i, total)
            
            # Get URLs
            urls = VoiceInstaller._get_voice_urls(voice_info)
            
            # Download files
            onnx_file = list(urls.keys())[0]  # First file is .onnx
            json_file = list(urls.keys())[1]  # Second file is .onnx.json
            
            onnx_path = models_dir / onnx_file
            json_path = models_dir / json_file
            
            # Skip if files already exist
            if onnx_path.exists() and json_path.exists():
                # Files already downloaded, just create preset
                try:
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    data["model_path"] = str(onnx_path.absolute())
                    preset_file = presets_dir / json_file
                    preset_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    installed_count += 1
                    continue
                except Exception:
                    pass  # Continue to re-download
            
            # Download .onnx file
            if not VoiceInstaller.download_voice_file(urls[onnx_file], onnx_path):
                # If download fails, skip this voice (might not exist)
                continue
            
            # Download .onnx.json file
            if not VoiceInstaller.download_voice_file(urls[json_file], json_path):
                # If JSON download fails, remove the onnx file
                if onnx_path.exists():
                    onnx_path.unlink()
                continue
            
            # Create preset in presets directory
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                # Update model_path to point to the downloaded .onnx file
                data["model_path"] = str(onnx_path.absolute())
                
                # Save preset to presets directory
                preset_file = presets_dir / json_file
                preset_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                
                installed_count += 1
            except Exception:
                # If preset creation fails, continue with next voice
                continue
        
        return installed_count
    
    @staticmethod
    def has_voices(presets_dir: Path) -> bool:
        """Check if any voices are already installed."""
        if not presets_dir.exists():
            return False
        return any(presets_dir.glob("*.onnx.json"))

