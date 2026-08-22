"""Meow OS Desktop — Voice Module."""

from .listener import VoiceListener
from .stt import WhisperSTT
from .tts import MacTTS
from .wake_word import WakeWordDetector

__all__ = ["VoiceListener", "WhisperSTT", "MacTTS", "WakeWordDetector"]
