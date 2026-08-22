"""Meow OS Desktop Application — Main Entry Point.

Launch with: python -m desktop.app
"""
import sys
import signal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from desktop.widget import MeowOSWindow
from desktop.tray import MeowTray
from desktop.bridge import MeowBridge
from desktop.voice.listener import VoiceListener
from desktop.voice.wake_word import WakeWordDetector
from desktop.voice.tts import MacTTS
from desktop.voice.stt import WhisperSTT

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Meow OS')
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray
    
    # Allow Ctrl+C to kill the app
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Initialize components
    bridge = MeowBridge()
    tts = MacTTS()
    stt = WhisperSTT()
    
    # Create main window
    window = MeowOSWindow(bridge=bridge, tts=tts)
    window.show()
    
    # System tray
    tray = MeowTray(app, window, bridge)
    tray.show()
    
    # Voice pipeline (optional — start if mic available)
    try:
        wake_detector = WakeWordDetector(stt=stt)
        listener = VoiceListener()
        
        # Wire: listener -> wake detector -> process command
        listener.audio_captured.connect(wake_detector.check_audio)
        wake_detector.wake_word_detected.connect(lambda: window.start_voice_command())
        wake_detector.transcription_ready.connect(lambda text: window.process_voice_command(text))
        
        listener.start()
    except Exception as e:
        print(f'Voice system unavailable: {e}')
    
    # Health check timer
    health_timer = QTimer()
    health_timer.timeout.connect(bridge.check_health)
    health_timer.start(30000)  # every 30s
    bridge.check_health()  # initial check
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
