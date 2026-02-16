"""
Braille Display Widget for Right Panel
Shows detected objects as Braille characters with 3x2 dot matrix
Sends patterns to ESP32 for physical solenoid actuation
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
import config
from braille_converter import BrailleConverter


class BrailleDotWidget(QWidget):
    """
    Widget to display a single Braille character as 3x2 dot matrix
    """
    
    def __init__(self, char='', dots=None, parent=None):
        super().__init__(parent)
        self.char = char
        self.dots = dots if dots is not None else []
        self.setMinimumSize(100, 150)
        
    def set_character(self, char, dots):
        """
        Set character and dot pattern
        """
        self.char = char
        self.dots = dots
        self.update()
    
    def paintEvent(self, event):
        """
        Paint the Braille dots
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.fillRect(self.rect(), QColor(config.BRAILLE_BG_COLOR))
        
        dot_size = config.BRAILLE_DOT_SIZE
        spacing = config.BRAILLE_DOT_SPACING
        
        start_x = (self.width() - (2 * dot_size + spacing)) // 2
        start_y = 40
        
        dot_positions = {
            1: (start_x, start_y),
            2: (start_x, start_y + dot_size + spacing),
            3: (start_x, start_y + 2 * (dot_size + spacing)),
            4: (start_x + dot_size + spacing, start_y),
            5: (start_x + dot_size + spacing, start_y + dot_size + spacing),
            6: (start_x + dot_size + spacing, start_y + 2 * (dot_size + spacing)),
        }
        
        for dot_num in range(1, 7):
            x, y = dot_positions[dot_num]
            
            if dot_num in self.dots:
                painter.setBrush(QColor(config.BRAILLE_RAISED_COLOR))
            else:
                painter.setBrush(QColor(config.BRAILLE_LOWERED_COLOR))
            
            painter.drawEllipse(x, y, dot_size, dot_size)
        
        painter.setPen(QColor("#000000"))
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignTop | Qt.AlignHCenter, self.char.upper())


class BrailleWidget(QWidget):
    """
    Main Braille display widget
    """
    
    braille_pattern_ready = pyqtSignal(str, list)
    
    def __init__(self, esp32_controller=None, parent=None):
        super().__init__(parent)
        self.esp32_controller = esp32_controller
        self.current_text = ""
        self.current_index = 0
        self.braille_chars = []
        self.converter = BrailleConverter()
        self.init_ui()
        
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.show_next_character)
        
    def init_ui(self):
        """
        Initialize UI components
        """
        layout = QVBoxLayout()
        
        self.title_label = QLabel("Braille Display")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; "
            "padding: 10px; background-color: #2196F3; color: white;"
        )
        layout.addWidget(self.title_label)
        
        self.text_label = QLabel("Waiting for detection...")
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("font-size: 16px; padding: 10px;")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none;")
        
        self.braille_container = QWidget()
        self.braille_layout = QVBoxLayout()
        self.braille_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.braille_container.setLayout(self.braille_layout)
        
        scroll_area.setWidget(self.braille_container)
        layout.addWidget(scroll_area)
        
        self.setLayout(layout)
        self.setStyleSheet("background-color: white;")
    
    def display_text(self, text):
        """
        Display text as Braille characters letter by letter
        
        Args:
            text: string to display
        """
        if text == self.current_text:
            return
        
        self.current_text = text
        self.current_index = 0
        
        self.text_label.setText(f"Detected: {text}")
        
        for i in reversed(range(self.braille_layout.count())):
            widget = self.braille_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        self.braille_chars = self.converter.text_to_braille(text)
        
        self.animation_timer.stop()
        self.animation_timer.start(config.BRAILLE_ANIMATION_SPEED)
    
    def show_next_character(self):
        """
        Show next character in animation sequence
        """
        if self.current_index >= len(self.braille_chars):
            self.animation_timer.stop()
            return
        
        char, dots = self.braille_chars[self.current_index]
        
        dot_widget = BrailleDotWidget(char, dots)
        self.braille_layout.addWidget(dot_widget)
        
        if self.esp32_controller and self.esp32_controller.is_connected:
            self.esp32_controller.send_character(char, dots)
        
        self.braille_pattern_ready.emit(char, dots)
        
        self.current_index += 1
    
    def clear_display(self):
        """
        Clear Braille display
        """
        self.current_text = ""
        self.current_index = 0
        self.animation_timer.stop()
        
        for i in reversed(range(self.braille_layout.count())):
            widget = self.braille_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        self.text_label.setText("Waiting for detection...")
        
        if self.esp32_controller and self.esp32_controller.is_connected:
            self.esp32_controller.reset_solenoids()
    
    def update_detections(self, detections):
        """
        Update display with new detections
        
        Args:
            detections: list of detection dictionaries
        """
        if not detections:
            return
        
        top_detection = max(detections, key=lambda x: x['confidence'])
        self.display_text(top_detection['label'])
