"""
Configuration settings for the Dynabraille application
"""

# Window settings
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900
WINDOW_TITLE = "Dynabraille - Object Detection & Braille Display"

# Layout proportions (left, center, right)
LEFT_PANEL_WIDTH = 640
CENTER_PANEL_WIDTH = 480
RIGHT_PANEL_WIDTH = 480

# YOLO settings
YOLO_MODEL = "yolov8n.pt"  # Options: yolov8n.pt (fastest), yolov8s.pt, yolov8m.pt, yolov8l.pt, yolov8x.pt (most accurate)
CONFIDENCE_THRESHOLD = 0.5
IOU_THRESHOLD = 0.45

# Camera settings
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
TARGET_FPS = 30

# Braille display settings
BRAILLE_DOT_SIZE = 20
BRAILLE_DOT_SPACING = 10
BRAILLE_CHAR_SPACING = 40
BRAILLE_ANIMATION_SPEED = 200  # milliseconds per character
BRAILLE_RAISED_COLOR = "#2196F3"  # Blue for raised dots
BRAILLE_LOWERED_COLOR = "#E0E0E0"  # Light gray for lowered dots
BRAILLE_BG_COLOR = "#FFFFFF"

# Chatbot settings
CHATBOT_MAX_HISTORY = 100
CHATBOT_USER_COLOR = "#E3F2FD"
CHATBOT_BOT_COLOR = "#F5F5F5"
