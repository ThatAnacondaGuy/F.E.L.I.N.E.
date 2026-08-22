"""Meow OS Desktop — Wake Word Detector."""

from PyQt6.QtCore import QObject, pyqtSignal
import numpy as np

class WakeWordDetector(QObject):
    wake_word_detected = pyqtSignal()
    transcription_ready = pyqtSignal(str)
    
    def __init__(self, stt):
        super().__init__()
        self.stt = stt
        self.cooldown = False
        
    def check_audio(self, audio_data: np.ndarray, sample_rate: int):
        if self.cooldown:
            return
            
        text = self.stt.transcribe(audio_data, sample_rate)
        if "hey meow" in text.lower():
            self.wake_word_detected.emit()
            command = text.lower().replace("hey meow", "").strip()
            if command:
                self.transcription_ready.emit(command)
