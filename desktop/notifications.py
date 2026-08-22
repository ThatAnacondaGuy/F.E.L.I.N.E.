"""Meow OS Desktop — macOS Notifications."""

import subprocess
import time

class MacNotifier:
    def __init__(self):
        self.last_notify_time = 0
        
    def notify(self, title, message, sound=True):
        now = time.time()
        if now - self.last_notify_time < 30:
            return
            
        script = f'display notification "{message}" with title "{title}"'
        if sound:
            script += ' sound name "Submarine"'
            
        subprocess.run(['osascript', '-e', script])
        self.last_notify_time = now
