"""Meow OS Desktop — Drag and Drop Handler."""

import os
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

class DragDropHandler(QObject):
    file_processed = pyqtSignal(str)
    
    def __init__(self, widget, bridge):
        super().__init__(widget)
        self.widget = widget
        self.bridge = bridge

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.widget.cat.set_state(self.widget.cat.state.ALERT)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
            
        event.acceptProposedAction()
        self.widget.cat.set_state(self.widget.cat.state.THINKING)
        
        filepath = urls[0].toLocalFile()
        if not filepath:
            self.widget.cat.set_state(self.widget.cat.state.IDLE)
            return
            
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".pdf":
            action = "Summarize this research paper's methodology"
        elif ext == ".py":
            action = "Review this code and suggest improvements"
        elif ext in [".txt", ".md"]:
            action = "Summarize the key points"
        else:
            action = "Describe this file"
            
        self.bridge.process_file_async(filepath, action)
