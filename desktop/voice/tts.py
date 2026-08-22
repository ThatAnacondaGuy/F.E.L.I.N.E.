"""Meow OS Desktop — Text-to-Speech."""

import subprocess
from PyQt6.QtCore import QThread, QObject

class TTSWorker(QThread):
    def __init__(self, text, voice="Samantha", rate="175"):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        
    def run(self):
        subprocess.run(['say', '-v', self.voice, '-r', self.rate, self.text])

class MacTTS(QObject):
    def __init__(self):
        super().__init__()
        self.is_speaking = False
        self.current_worker = None
        
    def speak(self, text):
        subprocess.Popen(['say', '-v', 'Samantha', '-r', '175', text])
        
    def speak_async(self, text):
        self.current_worker = TTSWorker(text)
        self.current_worker.start()
        
    def stop(self):
        if self.current_worker and self.current_worker.isRunning():
            subprocess.run(['killall', 'say'])
