"""
Camera Display Widget for Left Panel
Shows live camera feed with YOLO detections
"""
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap
import numpy as np


class CameraWidget(QWidget):
    """
    Widget for displaying camera feed with object detections
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """
        Initialize UI components
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #000000; border: 2px solid #2196F3;")
        self.video_label.setScaledContents(False)
        
        layout.addWidget(self.video_label)
        self.setLayout(layout)
    
    @pyqtSlot(np.ndarray, list)
    def update_frame(self, frame, detections):
        """
        Update displayed frame
        
        Args:
            frame: numpy array in RGB format
            detections: list of detection dictionaries
        """
        height, width, channel = frame.shape
        bytes_per_line = 3 * width
        
        q_image = QImage(
            frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888
        )
        
        pixmap = QPixmap.fromImage(q_image)
        
        scaled_pixmap = pixmap.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        self.video_label.setPixmap(scaled_pixmap)
    
    def show_no_camera(self):
        """
        Display message when camera is not available
        """
        self.video_label.setText("Camera Not Available")
        self.video_label.setStyleSheet(
            "background-color: #000000; color: #FFFFFF; "
            "font-size: 24px; border: 2px solid #F44336;"
        )
