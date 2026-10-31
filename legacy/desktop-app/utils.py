"""
Utility functions for the Dynabraille application
"""
import numpy as np
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt


def numpy_to_qpixmap(image):
    """
    Convert a numpy array (OpenCV image) to QPixmap for PyQt5 display
    
    Args:
        image: numpy array in BGR or RGB format
        
    Returns:
        QPixmap object
    """
    height, width, channel = image.shape
    bytes_per_line = 3 * width
    
    # Convert BGR to RGB if needed
    if channel == 3:
        rgb_image = image
    else:
        rgb_image = image
    
    q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
    return QPixmap.fromImage(q_image)


def bgr_to_rgb(image):
    """
    Convert BGR image to RGB
    
    Args:
        image: numpy array in BGR format
        
    Returns:
        numpy array in RGB format
    """
    import cv2
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def draw_detection_box(image, box, label, confidence):
    """
    Draw bounding box and label on image
    
    Args:
        image: numpy array (BGR format)
        box: tuple of (x1, y1, x2, y2)
        label: string label
        confidence: float confidence score
        
    Returns:
        image with drawn box
    """
    import cv2
    
    x1, y1, x2, y2 = map(int, box)
    
    # Draw rectangle
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
    
    # Draw label background
    label_text = f"{label} {confidence:.2f}"
    (text_width, text_height), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(image, (x1, y1 - text_height - 10), (x1 + text_width, y1), (0, 255, 0), -1)
    
    # Draw label text
    cv2.putText(image, label_text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    
    return image
