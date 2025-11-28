"""
Piper neural TTS integration using the piper-tts Python package.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

try:
    from piper.voice import PiperVoice
    PIPER_AVAILABLE = True
    PIPER_IMPORT_ERROR = None
except ImportError as e:
    PIPER_AVAILABLE = False
    PIPER_IMPORT_ERROR = str(e)
    PiperVoice = None


class PiperTTSError(Exception):
    """Generic Piper TTS error."""


def check_tts_availability() -> tuple[bool, Optional[str]]:
    """
    Check if TTS is available and return a user-friendly message if not.
    Returns: (is_available, error_message_or_none)
    """
    if PIPER_AVAILABLE:
        return True, None
    
    import sys
    error_msg = "TTS features are not available.\n\n"
    
    if PIPER_IMPORT_ERROR:
        if "onnxruntime" in str(PIPER_IMPORT_ERROR):
            error_msg += (
                "The 'onnxruntime' package is required but not available.\n\n"
                "If you're using Python 3.14, please use Python 3.13 or earlier.\n"
                "Otherwise, install with: pip install onnxruntime\n\n"
            )
        elif "piper_phonemize" in str(PIPER_IMPORT_ERROR):
            error_msg += (
                "The 'piper-phonemize' package is required but not available.\n\n"
                "piper-phonemize needs to be built from source and requires Rust.\n\n"
                "Installation steps:\n"
                "1. Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh\n"
                "2. Restart your terminal or run: source ~/.cargo/env\n"
                "3. Install piper-phonemize: pip install piper-phonemize\n"
                "   Or from source: pip install git+https://github.com/rhasspy/piper-phonemize.git\n\n"
            )
        else:
            error_msg += f"Error: {PIPER_IMPORT_ERROR}\n\n"
            error_msg += "Try installing: pip install piper-tts\n\n"
    
    error_msg += (
        "Note: TTS features will not work until dependencies are installed.\n"
        "All other app features should work normally.\n\n"
        f"Current Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    
    return False, error_msg


class PiperTTS:
    """
    Wrapper around the piper-tts Python package.
    Generates audio files from text using a selected Piper voice model.
    """

    def __init__(
        self, 
        model_path: Optional[str] = None,
        config_path: Optional[str] = None,
        speaker: Optional[int] = None,
        noise_scale: Optional[float] = None,
        length_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
        sentence_silence_seconds: Optional[float] = None
    ):
        if not PIPER_AVAILABLE:
            import sys
            error_msg = "piper-tts package dependencies are not available.\n\n"
            if "onnxruntime" in str(PIPER_IMPORT_ERROR):
                error_msg += (
                    "The 'onnxruntime' package is required but not available for Python 3.14.\n\n"
                    "Options:\n"
                    "1. Use Python 3.13 or earlier (recommended)\n"
                    "2. Wait for onnxruntime to support Python 3.14\n"
                    "3. Try installing from source: pip install onnxruntime --no-binary onnxruntime\n\n"
                )
            elif "piper_phonemize" in str(PIPER_IMPORT_ERROR):
                error_msg += (
                    "The 'piper-phonemize' package is required but not available.\n\n"
                    "piper-phonemize needs to be built from source and requires Rust.\n\n"
                    "Installation options:\n"
                    "1. Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh\n"
                    "2. Then install piper-phonemize: pip install piper-phonemize\n"
                    "   Or from source: pip install git+https://github.com/rhasspy/piper-phonemize.git\n\n"
                    "Note: TTS features will not work until piper-phonemize is installed.\n"
                    "All other app features should work normally.\n\n"
                )
            else:
                error_msg += f"Error: {PIPER_IMPORT_ERROR}\n\n"
                error_msg += "Install with: pip install piper-tts\n"
            
            error_msg += f"\nCurrent Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            raise PiperTTSError(error_msg)
        
        self._model_path = Path(model_path).expanduser() if model_path else None
        self._config_path = Path(config_path).expanduser() if config_path else None
        self._speaker = speaker
        self._noise_scale = noise_scale
        self._length_scale = length_scale
        self._noise_w = noise_w
        self._sentence_silence_seconds = sentence_silence_seconds
        self._piper_instance: Optional[PiperVoice] = None

    @property
    def model_path(self) -> Optional[Path]:
        return self._model_path

    def set_model(self, model_path: str, config_path: Optional[str] = None) -> None:
        path = Path(model_path).expanduser()
        if not path.exists():
            raise PiperTTSError(f"Piper model not found: {path}")
        self._model_path = path
        
        if config_path:
            config = Path(config_path).expanduser()
            if config.exists():
                self._config_path = config
        else:
            # Try to find config file automatically
            config = path.with_suffix('.onnx.json')
            if config.exists():
                self._config_path = config
        
        # Reset instance so it's recreated with new model
        self._piper_instance = None

    def set_speaker(self, speaker: Optional[int]) -> None:
        self._speaker = speaker
        # Reset instance so it's recreated with new speaker
        self._piper_instance = None

    def _get_piper_instance(self) -> PiperVoice:
        """Get or create the PiperVoice instance."""
        if self._piper_instance is None:
            if not self._model_path or not self._model_path.exists():
                raise PiperTTSError(
                    f"Piper model not configured or not found.\n\n"
                    f"Model path: {self._model_path}\n\n"
                    f"Please select a valid Piper TTS model file (.onnx) in the voice settings."
                )
            
            # Validate that this is likely a Piper model (not a random .onnx file)
            model_path_str = str(self._model_path)
            invalid_patterns = ["logreg_iris", "datasets", "onnxruntime/datasets", ".venv", "venv", "site-packages"]
            if any(pattern in model_path_str for pattern in invalid_patterns):
                raise PiperTTSError(
                    f"Invalid model path detected. The selected file appears to be a demo file or is located in a virtual environment, not a Piper TTS model.\n\n"
                    f"Model path: {self._model_path}\n\n"
                    f"Please select a valid Piper TTS voice model (.onnx file) in the voice settings.\n"
                    f"You may need to download Piper voice models first.\n\n"
                    f"Note: Model files should not be in .venv, venv, or site-packages directories."
                )
            
            # Initialize PiperVoice with model and optional config
            config_path = self._config_path
            if not config_path or not config_path.exists():
                # Try to find config file automatically
                config_path = self._model_path.with_suffix('.onnx.json')
                if not config_path.exists():
                    config_path = None
            
            if config_path and config_path.exists():
                self._piper_instance = PiperVoice.load(
                    model_path=str(self._model_path),
                    config_path=str(config_path)
                )
            else:
                self._piper_instance = PiperVoice.load(
                    model_path=str(self._model_path)
                )
        
        return self._piper_instance

    def is_available(self) -> bool:
        """Check if TTS is available."""
        if not PIPER_AVAILABLE:
            return False
        if not self._model_path or not self._model_path.exists():
            return False
        try:
            # Try to create instance to verify it works
            self._get_piper_instance()
            return True
        except Exception:
            return False

    def synthesize(self, text: str) -> Path:
        """
        Generate speech audio for the provided text.
        Returns a path to a temporary WAV file.
        """
        if not PIPER_AVAILABLE:
            import sys
            error_msg = "piper-tts package dependencies are not available.\n\n"
            if PIPER_IMPORT_ERROR and "onnxruntime" in PIPER_IMPORT_ERROR:
                error_msg += (
                    "The 'onnxruntime' package is required but not available for Python 3.14.\n\n"
                    "Please use Python 3.13 or earlier, or wait for onnxruntime to support Python 3.14."
                )
            elif PIPER_IMPORT_ERROR and "piper_phonemize" in PIPER_IMPORT_ERROR:
                error_msg += (
                    "The 'piper-phonemize' package is required but not available for Python 3.14.\n\n"
                    "Please use Python 3.13 or earlier, or wait for piper-phonemize to support Python 3.14."
                )
            else:
                error_msg += f"Error: {PIPER_IMPORT_ERROR or 'Unknown error'}\n\n"
                error_msg += "Install with: pip install piper-tts"
            raise PiperTTSError(error_msg)
        
        if not self._model_path:
            raise PiperTTSError("Piper model not configured.")

        try:
            import wave
            import os
            
            piper = self._get_piper_instance()
            
            # Create temporary WAV file
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="piper_tts_")
            os.close(tmp_fd)
            
            # Synthesize audio directly to WAV file
            with wave.open(tmp_path, 'wb') as wav_file:
                # Build synthesize arguments - only include speaker_id if it's not None
                # Some models don't support speaker IDs, so we need to handle that
                synthesize_kwargs = {
                    'text': text,
                    'wav_file': wav_file,
                    'length_scale': self._length_scale,
                    'noise_scale': self._noise_scale,
                    'noise_w': self._noise_w,
                    'sentence_silence': self._sentence_silence_seconds
                }
                
                # Only add speaker_id if it's not None (some models don't support it)
                if self._speaker is not None:
                    synthesize_kwargs['speaker_id'] = self._speaker
                
                try:
                    piper.synthesize(**synthesize_kwargs)
                except Exception as e:
                    # If speaker_id caused the error, try without it
                    if 'speaker_id' in synthesize_kwargs and ('sid' in str(e) or 'speaker' in str(e).lower()):
                        synthesize_kwargs.pop('speaker_id', None)
                        piper.synthesize(**synthesize_kwargs)
                    else:
                        raise
            
            output_path = Path(tmp_path)
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise PiperTTSError("Piper did not produce a valid output file.")
            
            return output_path
            
        except Exception as e:
            if isinstance(e, PiperTTSError):
                raise
            raise PiperTTSError(f"Failed to synthesize speech: {e}") from e

