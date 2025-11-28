# core/prerender_manager.py
"""
Prerender manager for TTS audio generation and caching.
"""
from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, Optional, Any, Callable

from core.nlp_processor import ScriptParse, DialogueBlock
from core.tts import PiperTTS, PiperTTSError
from core.project_manager import ProjectLibrary, Project
from app.tabs.voice_selection_dialog import VoiceConfig


MANIFEST_FILE = "manifest.json"
PRERENDER_DIR = "prerendered_audio"


class PrerenderManager:
    """Manages prerendered TTS audio for projects."""
    
    def __init__(self, project_library: ProjectLibrary):
        self.project_library = project_library
    
    def get_prerender_dir(self, project: Project) -> Path:
        """Get the prerender directory for a project."""
        # attachment_path returns a file path, but we need a directory
        # So we'll create the directory path manually
        attach_dir = self.project_library._attach_dir
        return attach_dir / f"{project.id}_{PRERENDER_DIR}"
    
    def get_manifest_path(self, project: Project) -> Path:
        """Get the manifest file path for a project."""
        prerender_dir = self.get_prerender_dir(project)
        return prerender_dir / MANIFEST_FILE
    
    def _hash_script(self, script_parse: ScriptParse) -> str:
        """Generate a hash of the script content."""
        # Hash all block text in order
        content = "\n".join(f"{block.speaker}:{block.text}" for block in script_parse.blocks)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _hash_voice_configs(self, voice_configs: Dict[str, VoiceConfig]) -> str:
        """Generate a hash of voice configurations."""
        # Create a sorted dict of voice configs for consistent hashing
        config_data = {}
        for char in sorted(voice_configs.keys()):
            vc = voice_configs[char]
            config_data[char] = {
                "model_path": str(vc.model_path) if vc.model_path else "",
                "speaker": vc.speaker,
                "noise_scale": vc.noise_scale,
                "length_scale": vc.length_scale,
                "noise_w": vc.noise_w,
                "sentence_silence_seconds": vc.sentence_silence_seconds,
            }
        content = json.dumps(config_data, sort_keys=True)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def load_manifest(self, project: Project) -> Optional[Dict[str, Any]]:
        """Load the manifest file for a project."""
        manifest_path = self.get_manifest_path(project)
        if not manifest_path.exists():
            return None
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def save_manifest(self, project: Project, manifest: Dict[str, Any]) -> None:
        """Save the manifest file for a project."""
        manifest_path = self.get_manifest_path(project)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    def is_prerender_valid(self, project: Project, script_parse: ScriptParse, 
                          voice_configs: Dict[str, VoiceConfig]) -> bool:
        """Check if prerendered audio is valid for the current script and voices."""
        manifest = self.load_manifest(project)
        if not manifest:
            return False
        
        current_script_hash = self._hash_script(script_parse)
        current_voice_hash = self._hash_voice_configs(voice_configs)
        
        return (manifest.get('script_hash') == current_script_hash and
                manifest.get('voice_hash') == current_voice_hash)
    
    def get_prerendered_audio_path(self, project: Project, block_index: int) -> Optional[Path]:
        """Get the path to prerendered audio for a block, if it exists."""
        manifest = self.load_manifest(project)
        if not manifest:
            return None
        
        audio_files = manifest.get('audio_files', {})
        audio_file = audio_files.get(str(block_index))
        if not audio_file:
            return None
        
        # Audio files are stored in the prerender directory
        prerender_dir = self.get_prerender_dir(project)
        audio_path = prerender_dir / audio_file
        
        # Verify the path exists and is a file
        if audio_path.exists() and audio_path.is_file():
            return audio_path
        return None
    
    def clear_prerender(self, project: Project) -> None:
        """Clear all prerendered audio for a project."""
        prerender_dir = self.get_prerender_dir(project)
        if prerender_dir.exists():
            shutil.rmtree(prerender_dir)
    
    def prerender_all_blocks(
        self,
        project: Project,
        script_parse: ScriptParse,
        voice_configs: Dict[str, VoiceConfig],
        default_model_path: Optional[str],
        progress_callback: Optional[Callable[[int, int, str], Optional[bool]]] = None
    ) -> bool:
        """
        Prerender all dialogue blocks.
        
        Args:
            project: The project to prerender for
            script_parse: The parsed script
            voice_configs: Voice configurations for each character
            default_model_path: Default TTS model path
            progress_callback: Optional callback(block_index, total_blocks, message)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear old prerender
            self.clear_prerender(project)
            
            # Create prerender directory
            prerender_dir = self.get_prerender_dir(project)
            prerender_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate hashes
            script_hash = self._hash_script(script_parse)
            voice_hash = self._hash_voice_configs(voice_configs)
            
            # Prepare blocks
            blocks_to_render = []
            for block in script_parse.blocks:
                character = block.speaker
                if character in voice_configs:
                    voice_config = voice_configs[character]
                    blocks_to_render.append((block, voice_config))
                else:
                    # Use first available voice config as fallback
                    if voice_configs:
                        fallback_voice = list(voice_configs.values())[0]
                        blocks_to_render.append((block, fallback_voice))
                    else:
                        # Skip if no voice configs available
                        continue
            
            total_blocks = len(blocks_to_render)
            audio_files = {}
            
            # Render each block
            for block_index, (block, voice_config) in enumerate(blocks_to_render):
                if progress_callback:
                    result = progress_callback(block_index, total_blocks, 
                                    f"Rendering {block.speaker}: {block.text[:50]}...")
                    if result is False:  # User cancelled
                        raise InterruptedError("Prerendering cancelled by user")
                
                # Resolve model path
                model_path = voice_config.model_path
                if not model_path or not model_path.strip() or not Path(model_path).exists():
                    model_path = default_model_path
                
                if not model_path or not model_path.strip() or not Path(model_path).exists():
                    # Try auto-discovery
                    from app.tabs.voice_selection_dialog import VoicePresets
                    discovered_model = VoicePresets._find_onnx_model(None)
                    if discovered_model and Path(discovered_model).exists():
                        model_path = discovered_model
                    else:
                        raise PiperTTSError(
                            f"No valid model path for {block.speaker}. "
                            "Please configure a voice model."
                        )
                
                # Find config file
                config_path = None
                model_path_obj = Path(model_path)
                if model_path_obj.exists():
                    config_path_obj = model_path_obj.with_suffix('.onnx.json')
                    if config_path_obj.exists():
                        config_path = str(config_path_obj)
                
                # Create TTS instance
                tts = PiperTTS(
                    model_path=model_path,
                    config_path=config_path,
                    speaker=voice_config.speaker,
                    noise_scale=voice_config.noise_scale,
                    length_scale=voice_config.length_scale,
                    noise_w=voice_config.noise_w,
                    sentence_silence_seconds=voice_config.sentence_silence_seconds
                )
                
                if not tts.is_available():
                    raise PiperTTSError(
                        f"TTS not available for {block.speaker}. "
                        f"Model: {model_path}"
                    )
                
                # Prepare text (character name + dialogue, but not for narrator)
                if block.speaker == "NARRATOR":
                    text = block.text
                else:
                    text = f"{block.speaker}. {block.text}"
                
                # Generate audio
                temp_audio_path = tts.synthesize(text)
                
                # Move to prerender directory
                audio_filename = f"block_{block_index}.wav"
                audio_path = prerender_dir / audio_filename
                shutil.move(str(temp_audio_path), str(audio_path))
                
                # Store relative path in manifest
                audio_files[str(block_index)] = audio_filename
            
            # Save manifest
            manifest = {
                'script_hash': script_hash,
                'voice_hash': voice_hash,
                'audio_files': audio_files,
                'total_blocks': total_blocks,
            }
            self.save_manifest(project, manifest)
            
            if progress_callback:
                progress_callback(total_blocks, total_blocks, "Prerendering complete!")
            
            return True
            
        except Exception as e:
            # Clean up on error
            self.clear_prerender(project)
            raise PiperTTSError(f"Failed to prerender audio: {e}") from e

