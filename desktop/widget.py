"""Meow OS Desktop Entity — The Cat Widget.

A frameless, transparent, always-on-top PyQt6 window that serves as
the primary interface for Meow OS. The cat lives on your desktop,
responds to voice, accepts drag-and-drop, and displays notifications.
"""
import sys
import os
import json
import logging
import math
import random
from pathlib import Path
from enum import Enum
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QSystemTrayIcon, QMenu, QTextEdit, QLineEdit,
    QGraphicsOpacityEffect, QSizePolicy, QFrame
)
from PyQt6.QtCore import (
    Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve,
    QSize, pyqtSignal, QThread, QUrl, QMimeData, QRect
)
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QFont, QIcon, QAction,
    QMouseEvent, QPaintEvent, QDragEnterEvent, QDropEvent,
    QLinearGradient, QRadialGradient, QPen, QBrush, QPainterPath
)
from desktop.drag_drop import DragDropHandler

logger = logging.getLogger(__name__)

class CatState(Enum):
    IDLE = "idle"
    THINKING = "thinking" 
    SPEAKING = "speaking"
    LISTENING = "listening"
    ALERT = "alert"
    SLEEPING = "sleeping"
    FOCUS = "focus"
    HAPPY = "happy"

class CatWidget(QWidget):
    """The cat character rendered via QPainter — no external images needed."""
    
    state_changed = pyqtSignal(CatState)
    message_received = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = CatState.IDLE
        self._animation_frame = 0
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._animate)
        self._blink_timer.start(100)  # 10fps animation
        self._is_blinking = False
        self._blink_counter = 0
        self._tail_angle = 0
        self._ear_wiggle = 0
        self._breathing_phase = 0
        self.setMinimumSize(120, 140)
    
    def set_state(self, state: CatState):
        self.state = state
        self.state_changed.emit(state)
        self.update()
    
    def _animate(self):
        self._animation_frame += 1
        self._breathing_phase = (self._breathing_phase + 1) % 60
        self._tail_angle = 15 * math.sin(self._animation_frame * 0.05)
        
        # Random blinking
        self._blink_counter += 1
        if self._blink_counter > 40 and not self._is_blinking:  # ~4 seconds
            if random.random() < 0.1:
                self._is_blinking = True
                self._blink_counter = 0
        if self._is_blinking:
            self._blink_counter += 1
            if self._blink_counter > 3:
                self._is_blinking = False
                self._blink_counter = 0
        
        # Ear wiggle when listening
        if self.state == CatState.LISTENING:
            self._ear_wiggle = 5 * math.sin(self._animation_frame * 0.3)
        else:
            self._ear_wiggle *= 0.9  # dampen
        
        self.update()
    
    def paintEvent(self, event: QPaintEvent):
        """Draw the cat using QPainter — pure vector art, no images needed."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2 + 10  # center of cat body
        
        # Breathing offset
        breath = 2 * math.sin(self._breathing_phase * 0.1)
        
        # Colors based on state
        body_color = QColor('#2d2d3d')  # dark charcoal cat
        accent_color = self._get_accent_color()
        eye_color = accent_color
        
        # === TAIL ===
        painter.setPen(QPen(body_color, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        tail_start_x = cx + 30
        tail_start_y = cy + 25
        # Draw curved tail using cubic bezier
        tail_path = QPainterPath()
        tail_path.moveTo(tail_start_x, tail_start_y)
        tail_path.cubicTo(
            tail_start_x + 25, tail_start_y - 10 + self._tail_angle,
            tail_start_x + 35, tail_start_y - 30 + self._tail_angle,
            tail_start_x + 20, tail_start_y - 45 + self._tail_angle
        )
        painter.drawPath(tail_path)
        
        # === BODY (oval) ===
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(body_color))
        body_rect_x = cx - 32
        body_rect_y = cy - 10 + breath
        painter.drawEllipse(body_rect_x, int(body_rect_y), 64, 45)
        
        # === HEAD (circle) ===
        head_y = cy - 35 + breath
        painter.drawEllipse(cx - 28, int(head_y), 56, 48)
        
        # === EARS (triangles) ===
        ear_offset = self._ear_wiggle
        # Left ear
        left_ear = [QPoint(cx - 22, int(head_y + 8)), QPoint(cx - 28 + int(ear_offset), int(head_y - 18)), QPoint(cx - 8, int(head_y + 2))]
        painter.drawPolygon(left_ear)
        # Right ear
        right_ear = [QPoint(cx + 22, int(head_y + 8)), QPoint(cx + 28 - int(ear_offset), int(head_y - 18)), QPoint(cx + 8, int(head_y + 2))]
        painter.drawPolygon(right_ear)
        
        # Inner ears (accent color)
        painter.setBrush(QBrush(accent_color.darker(150)))
        inner_left = [QPoint(cx - 20, int(head_y + 6)), QPoint(cx - 24 + int(ear_offset), int(head_y - 12)), QPoint(cx - 10, int(head_y + 2))]
        painter.drawPolygon(inner_left)
        inner_right = [QPoint(cx + 20, int(head_y + 6)), QPoint(cx + 24 - int(ear_offset), int(head_y - 12)), QPoint(cx + 10, int(head_y + 2))]
        painter.drawPolygon(inner_right)
        
        # === EYES ===
        eye_y = int(head_y + 18)
        if self._is_blinking or self.state == CatState.SLEEPING:
            # Closed eyes — horizontal lines
            painter.setPen(QPen(eye_color, 2))
            painter.drawLine(cx - 16, eye_y, cx - 8, eye_y)
            painter.drawLine(cx + 8, eye_y, cx + 16, eye_y)
        elif self.state == CatState.FOCUS:
            # Narrow focused eyes
            painter.setBrush(QBrush(eye_color))
            painter.drawEllipse(cx - 16, eye_y - 2, 8, 4)
            painter.drawEllipse(cx + 8, eye_y - 2, 8, 4)
        else:
            # Open eyes — large, glowing
            painter.setBrush(QBrush(eye_color))
            painter.drawEllipse(cx - 17, eye_y - 5, 10, 10)
            painter.drawEllipse(cx + 7, eye_y - 5, 10, 10)
            # Pupils
            painter.setBrush(QBrush(QColor('#0a0e17')))
            pupil_offset = 1 if self.state == CatState.THINKING else 0
            painter.drawEllipse(cx - 14 + pupil_offset, eye_y - 2, 4, 4)
            painter.drawEllipse(cx + 10 + pupil_offset, eye_y - 2, 4, 4)
            # Eye shine
            painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
            painter.drawEllipse(cx - 13, eye_y - 4, 2, 2)
            painter.drawEllipse(cx + 11, eye_y - 4, 2, 2)
        
        # === NOSE ===
        painter.setBrush(QBrush(QColor('#ff8fa3')))
        painter.drawEllipse(cx - 3, eye_y + 8, 6, 4)
        
        # === MOUTH ===
        painter.setPen(QPen(QColor('#ff8fa3'), 1.5))
        if self.state == CatState.SPEAKING:
            # Open mouth
            painter.drawEllipse(cx - 4, eye_y + 13, 8, 5)
        elif self.state == CatState.HAPPY:
            # Smile with fangs
            smile = QPainterPath()
            smile.moveTo(cx - 6, eye_y + 13)
            smile.quadTo(cx, eye_y + 18, cx + 6, eye_y + 13)
            painter.drawPath(smile)
        else:
            # Neutral :3 mouth
            painter.drawLine(cx, eye_y + 12, cx - 5, eye_y + 15)
            painter.drawLine(cx, eye_y + 12, cx + 5, eye_y + 15)
        
        # === WHISKERS ===
        painter.setPen(QPen(QColor('#9ca3af'), 1))
        whisker_y = eye_y + 10
        # Left whiskers
        painter.drawLine(cx - 25, whisker_y - 3, cx - 45, whisker_y - 8)
        painter.drawLine(cx - 25, whisker_y, cx - 47, whisker_y)
        painter.drawLine(cx - 25, whisker_y + 3, cx - 45, whisker_y + 8)
        # Right whiskers
        painter.drawLine(cx + 25, whisker_y - 3, cx + 45, whisker_y - 8)
        painter.drawLine(cx + 25, whisker_y, cx + 47, whisker_y)
        painter.drawLine(cx + 25, whisker_y + 3, cx + 45, whisker_y + 8)
        
        # === PAWS (front) ===
        painter.setBrush(QBrush(body_color))
        painter.setPen(Qt.PenStyle.NoPen)
        paw_y = cy + 30 + breath
        painter.drawEllipse(cx - 22, int(paw_y), 16, 10)
        painter.drawEllipse(cx + 6, int(paw_y), 16, 10)
        
        # === STATE INDICATOR (glowing ring around cat when active) ===
        if self.state not in (CatState.IDLE, CatState.SLEEPING):
            glow_color = QColor(accent_color)
            glow_color.setAlpha(40 + int(20 * math.sin(self._animation_frame * 0.1)))
            painter.setPen(QPen(glow_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(cx - 40, int(head_y - 22), 80, 80)
        
        painter.end()
    
    def _get_accent_color(self) -> QColor:
        colors = {
            CatState.IDLE: QColor('#00d4ff'),      # cyan
            CatState.THINKING: QColor('#7c3aed'),   # purple
            CatState.SPEAKING: QColor('#00d4ff'),   # cyan
            CatState.LISTENING: QColor('#10b981'),   # green
            CatState.ALERT: QColor('#f59e0b'),       # amber
            CatState.SLEEPING: QColor('#6b7280'),    # gray
            CatState.FOCUS: QColor('#ef4444'),        # red
            CatState.HAPPY: QColor('#10b981'),        # green
        }
        return colors.get(self.state, QColor('#00d4ff'))


class MeowOSWindow(QWidget):
    """The main transparent, frameless window holding the Cat Widget and chat interfaces."""
    
    def __init__(self, bridge, tts, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.tts = tts
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Accept drops
        self.setAcceptDrops(True)
        self.drag_handler = DragDropHandler(self, self.bridge)
        self.drag_handler.file_processed.connect(self.on_file_processed)

        self._drag_pos = QPoint()
        
        # Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # Chat Bubble
        self.chat_bubble = QLabel("")
        self.chat_bubble.setWordWrap(True)
        self.chat_bubble.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 30, 40, 220);
                color: #ffffff;
                border-radius: 10px;
                padding: 10px;
                font-family: Arial;
                font-size: 14px;
            }
        """)
        self.chat_bubble.hide()
        self.layout.addWidget(self.chat_bubble)
        
        # Cat
        self.cat = CatWidget()
        self.layout.addWidget(self.cat, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Status Label
        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.status_label)
        
        # Input Field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Meow at me...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 30, 40, 220);
                color: white;
                border: 1px solid #7c3aed;
                border-radius: 15px;
                padding: 5px 10px;
            }
        """)
        self.input_field.returnPressed.connect(self.send_chat)
        self.input_field.hide()
        self.layout.addWidget(self.input_field)
        
        self.chat_timer = QTimer()
        self.chat_timer.timeout.connect(self.hide_chat)
        
        # Load position
        self.config_path = Path.home() / ".meow_os_pos.json"
        self.load_position()
        
        # Signals
        self.bridge.chat_received.connect(self.on_chat_response)
        self.cat.state_changed.connect(self.on_cat_state_change)

    def load_position(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    pos = json.load(f)
                    self.move(pos.get("x", 100), pos.get("y", 100))
            except Exception as e:
                logger.error(f"Error loading position: {e}")
    
    def save_position(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump({"x": self.pos().x(), "y": self.pos().y()}, f)
        except Exception as e:
            logger.error(f"Error saving position: {e}")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            
    def mouseReleaseEvent(self, event: QMouseEvent):
        self.save_position()
        event.accept()
        
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # Toggle input field
        if self.input_field.isHidden():
            self.input_field.show()
            self.input_field.setFocus()
        else:
            self.input_field.hide()
            
    def dragEnterEvent(self, event: QDragEnterEvent):
        self.drag_handler.dragEnterEvent(event)
        
    def dropEvent(self, event: QDropEvent):
        self.drag_handler.dropEvent(event)
        
    def show_chat(self, text: str):
        self.chat_bubble.setText(text)
        self.chat_bubble.show()
        self.chat_timer.start(8000)
        
    def hide_chat(self):
        self.chat_bubble.hide()
        self.chat_timer.stop()
        
    def send_chat(self):
        text = self.input_field.text().strip()
        if text:
            self.cat.set_state(CatState.THINKING)
            self.input_field.clear()
            self.input_field.hide()
            self.bridge.send_chat_async(text)
            
    def on_chat_response(self, text: str):
        self.cat.set_state(CatState.SPEAKING)
        self.show_chat(text)
        self.tts.speak_async(text)
        # return to idle after some time
        QTimer.singleShot(len(text) * 50 + 1000, lambda: self.cat.set_state(CatState.IDLE))
        
    def on_file_processed(self, response: str):
        self.on_chat_response(response)
        
    def on_cat_state_change(self, state: CatState):
        self.status_label.setText(state.value.capitalize() + "...")
        if state == CatState.IDLE:
            self.status_label.setText("Idle")
            
    def start_voice_command(self):
        self.cat.set_state(CatState.LISTENING)
        
    def process_voice_command(self, text: str):
        if text:
            self.cat.set_state(CatState.THINKING)
            self.bridge.send_chat_async(text)
        else:
            self.cat.set_state(CatState.IDLE)
