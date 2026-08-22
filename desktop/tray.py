"""Meow OS Desktop — System Tray."""

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt

class MeowTray(QSystemTrayIcon):
    def __init__(self, app, window, bridge):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor('#7c3aed'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        
        super().__init__(QIcon(pixmap), app)
        self.app = app
        self.window = window
        self.bridge = bridge
        
        self.setToolTip("Meow OS")
        
        self.menu = QMenu()
        
        toggle_action = self.menu.addAction("Show/Hide Cat")
        toggle_action.triggered.connect(self.toggle_window)
        
        dash_action = self.menu.addAction("Dashboard")
        dash_action.triggered.connect(self.open_dashboard)
        
        quit_action = self.menu.addAction("Quit Meow OS")
        quit_action.triggered.connect(self.app.quit)
        
        self.setContextMenu(self.menu)
        
    def toggle_window(self):
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.show()
            
    def open_dashboard(self):
        import webbrowser
        webbrowser.open("http://127.0.0.1:8000")
