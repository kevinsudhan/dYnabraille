"""
Chatbot Widget for Center Panel
Interactive chat interface with message history
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, 
                             QLineEdit, QPushButton, QScrollArea, QLabel)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from chatbot_engine import ChatbotEngine
import config


class ChatMessage(QWidget):
    """
    Single chat message bubble
    """
    
    def __init__(self, message, is_user=True, parent=None):
        super().__init__(parent)
        self.message = message
        self.is_user = is_user
        self.init_ui()
    
    def init_ui(self):
        """
        Initialize message bubble UI
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        
        label = QLabel(self.message)
        label.setWordWrap(True)
        label.setFont(QFont("Arial", 11))
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        if self.is_user:
            label.setStyleSheet(f"""
                background-color: {config.CHATBOT_USER_COLOR};
                padding: 10px;
                border-radius: 10px;
                border: 1px solid #2196F3;
            """)
            label.setAlignment(Qt.AlignRight)
        else:
            label.setStyleSheet(f"""
                background-color: {config.CHATBOT_BOT_COLOR};
                padding: 10px;
                border-radius: 10px;
                border: 1px solid #CCCCCC;
            """)
            label.setAlignment(Qt.AlignLeft)
        
        layout.addWidget(label)
        self.setLayout(layout)


class ChatbotWidget(QWidget):
    """
    Main chatbot interface widget
    """
    
    message_sent = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chatbot = ChatbotEngine()
        self.init_ui()
        self.add_welcome_message()
        
    def init_ui(self):
        """
        Initialize UI components
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("Dynabraille Assistant")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; "
            "padding: 10px; background-color: #4CAF50; color: white;"
        )
        layout.addWidget(title_label)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: white;")
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout()
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(5)
        self.chat_container.setLayout(self.chat_layout)
        
        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area)
        
        input_container = QWidget()
        input_layout = QVBoxLayout()
        input_layout.setContentsMargins(10, 10, 10, 10)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message here...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                font-size: 14px;
                border: 2px solid #2196F3;
                border-radius: 5px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
            }
        """)
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        input_container.setLayout(input_layout)
        
        layout.addWidget(input_container)
        self.setLayout(layout)
        self.setStyleSheet("background-color: white;")
    
    def add_welcome_message(self):
        """
        Add welcome message from bot
        """
        welcome_text = ("Welcome to Dynabraille! I'm your assistant for object detection and Braille display. "
                       "Ask me anything about the detected objects or how the system works!")
        self.add_message(welcome_text, is_user=False)
    
    def add_message(self, message, is_user=True):
        """
        Add message to chat history
        
        Args:
            message: message text
            is_user: True if user message, False if bot message
        """
        message_widget = ChatMessage(message, is_user)
        self.chat_layout.addWidget(message_widget)
        
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )
    
    def send_message(self):
        """
        Send user message and get bot response
        """
        message = self.input_field.text().strip()
        
        if not message:
            return
        
        self.add_message(message, is_user=True)
        self.input_field.clear()
        
        self.message_sent.emit(message)
        
        response = self.chatbot.get_response(message)
        self.add_message(response, is_user=False)
    
    def notify_detection(self, label):
        """
        Notify chatbot of new detection
        
        Args:
            label: detected object label
        """
        notification = f"🔍 Detected: {label}"
        self.add_message(notification, is_user=False)
    
    def clear_chat(self):
        """
        Clear chat history
        """
        for i in reversed(range(self.chat_layout.count())):
            widget = self.chat_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        self.chatbot.clear_history()
        self.add_welcome_message()
