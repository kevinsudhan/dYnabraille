"""
Main Application Entry Point
Three-window layout with YOLO detection, Braille display, and chatbot
"""
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, 
                             QHBoxLayout, QVBoxLayout, QSplitter, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QIcon
import config
from yolo_detector import YOLODetector
from camera_widget import CameraWidget
from braille_widget import BrailleWidget
from chatbot_widget import ChatbotWidget
from esp32_controller import ESP32Controller


class MainWindow(QMainWindow):
    """
    Main application window with three panels
    """
    
    def __init__(self):
        super().__init__()
        self.yolo_detector = None
        self.esp32_controller = None
        self.init_hardware()
        self.init_ui()
        self.connect_signals()
        self.start_detection()
        
    def init_hardware(self):
        """
        Initialize hardware controllers
        """
        self.esp32_controller = ESP32Controller()
        
        try:
            if self.esp32_controller.connect():
                print("ESP32 connected successfully")
            else:
                print("ESP32 not connected - running in simulation mode")
        except Exception as e:
            print(f"ESP32 initialization error: {e}")
    
    def init_ui(self):
        """
        Initialize user interface
        """
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setGeometry(100, 100, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Horizontal)
        
        self.camera_widget = CameraWidget()
        self.camera_widget.setMinimumWidth(config.LEFT_PANEL_WIDTH)
        
        self.chatbot_widget = ChatbotWidget()
        self.chatbot_widget.setMinimumWidth(config.CENTER_PANEL_WIDTH)
        
        self.braille_widget = BrailleWidget(self.esp32_controller)
        self.braille_widget.setMinimumWidth(config.RIGHT_PANEL_WIDTH)
        
        splitter.addWidget(self.camera_widget)
        splitter.addWidget(self.chatbot_widget)
        splitter.addWidget(self.braille_widget)
        
        splitter.setSizes([
            config.LEFT_PANEL_WIDTH,
            config.CENTER_PANEL_WIDTH,
            config.RIGHT_PANEL_WIDTH
        ])
        
        main_layout.addWidget(splitter)
        central_widget.setLayout(main_layout)
        
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F5F5;
            }
            QSplitter::handle {
                background-color: #CCCCCC;
                width: 2px;
            }
        """)
    
    def connect_signals(self):
        """
        Connect signals between components
        """
        pass
    
    def start_detection(self):
        """
        Start YOLO detection thread
        """
        self.yolo_detector = YOLODetector()
        
        self.yolo_detector.frame_ready.connect(self.camera_widget.update_frame)
        self.yolo_detector.detection_ready.connect(self.handle_detections)
        self.yolo_detector.error_occurred.connect(self.handle_error)
        
        self.yolo_detector.start()
    
    @pyqtSlot(list)
    def handle_detections(self, detections):
        """
        Handle new detections from YOLO
        
        Args:
            detections: list of detection dictionaries
        """
        if detections:
            self.braille_widget.update_detections(detections)
            
            top_detection = max(detections, key=lambda x: x['confidence'])
            self.chatbot_widget.notify_detection(top_detection['label'])
    
    @pyqtSlot(str)
    def handle_error(self, error_message):
        """
        Handle errors from detection thread
        
        Args:
            error_message: error description
        """
        print(f"Error: {error_message}")
    
    def closeEvent(self, event):
        """
        Handle application close event
        """
        if self.yolo_detector:
            self.yolo_detector.stop()
            self.yolo_detector.wait()
        
        if self.esp32_controller:
            self.esp32_controller.reset_solenoids()
            self.esp32_controller.disconnect()
        
        event.accept()


def main():
    """
    Application entry point
    """
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
