"""Meow OS Desktop — Voice Listener."""

from PyQt6.QtCore import QThread, pyqtSignal
import numpy as np
import time

class VoiceListener(QThread):
    audio_captured = pyqtSignal(np.ndarray, int)
    
    def __init__(self):
        super().__init__()
        self.running = False
        
    def run(self):
        self.running = True
        try:
            import sounddevice as sd
        except ImportError:
            print("sounddevice not installed. Voice listener disabled.")
            return

        samplerate = 16000
        while self.running:
            time.sleep(1)
            # Placeholder for VAD
            
    def stop(self):
        self.running = False
