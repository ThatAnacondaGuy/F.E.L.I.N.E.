"""Meow OS Desktop — Backend Bridge."""

import urllib.request
import urllib.error
import urllib.parse
import json
from PyQt6.QtCore import QObject, pyqtSignal, QThread

class NetworkWorker(QThread):
    result_ready = pyqtSignal(dict)
    
    def __init__(self, url, method="GET", data=None):
        super().__init__()
        self.url = url
        self.method = method
        self.data = data
        
    def run(self):
        try:
            req = urllib.request.Request(self.url, method=self.method)
            req.add_header('Content-Type', 'application/json')
            
            data_bytes = None
            if self.data:
                data_bytes = json.dumps(self.data).encode('utf-8')
                
            with urllib.request.urlopen(req, data=data_bytes, timeout=5) as response:
                resp_text = response.read().decode('utf-8')
                self.result_ready.emit({"status": "ok", "data": json.loads(resp_text)})
        except Exception as e:
            self.result_ready.emit({"status": "error", "error": str(e)})

class MeowBridge(QObject):
    health_status = pyqtSignal(bool)
    chat_received = pyqtSignal(str)
    
    def __init__(self, base_url="http://127.0.0.1:8000"):
        super().__init__()
        self.base_url = base_url
        self.workers = []
        
    def check_health(self):
        worker = NetworkWorker(f"{self.base_url}/api/health")
        worker.result_ready.connect(self._on_health_result)
        self.workers.append(worker)
        worker.start()
        
    def _on_health_result(self, res):
        is_healthy = res.get("status") == "ok"
        self.health_status.emit(is_healthy)
        
    def send_chat_async(self, message: str):
        worker = NetworkWorker(
            f"{self.base_url}/api/chat", 
            method="POST", 
            data={"message": message}
        )
        worker.result_ready.connect(self._on_chat_result)
        self.workers.append(worker)
        worker.start()
        
    def _on_chat_result(self, res):
        if res.get("status") == "ok":
            text = res["data"].get("response", "Meow! I don't know what to say.")
            self.chat_received.emit(text)
        else:
            self.chat_received.emit("Error communicating with backend.")

    def process_file_async(self, filepath: str, action: str):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(1000)
            self.send_chat_async(f"{action}: {content}")
        except Exception as e:
            self.chat_received.emit(f"Could not read file: {e}")
