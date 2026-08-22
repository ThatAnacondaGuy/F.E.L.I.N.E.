"""Meow OS Desktop — Speech-to-Text."""

import numpy as np

class WhisperSTT:
    def __init__(self):
        self.model = None
        
    def _load_model(self):
        if not self.model:
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
            except ImportError:
                print("faster-whisper not installed.")
                
    def transcribe(self, audio_array: np.ndarray, sample_rate: int) -> str:
        self._load_model()
        if not self.model:
            return ""
        segments, info = self.model.transcribe(audio_array, beam_size=5)
        text = " ".join([segment.text for segment in segments])
        return text
