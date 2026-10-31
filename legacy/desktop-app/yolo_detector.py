"""
YOLO Object Detection Module
Handles camera capture and real-time object detection using YOLOv8
"""
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from ultralytics import YOLO
import config


class YOLODetector(QThread):
    """
    Thread for running YOLO object detection on camera feed
    """
    
    frame_ready = pyqtSignal(np.ndarray, list)
    detection_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.model = None
        self.camera = None
        self.current_detections = []
        
    def load_model(self):
        """
        Load YOLO model
        """
        try:
            self.model = YOLO(config.YOLO_MODEL)
            print(f"YOLO model {config.YOLO_MODEL} loaded successfully")
            return True
        except Exception as e:
            self.error_occurred.emit(f"Failed to load YOLO model: {str(e)}")
            return False
    
    def init_camera(self):
        """
        Initialize camera capture
        """
        try:
            self.camera = cv2.VideoCapture(config.CAMERA_INDEX)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
            self.camera.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
            
            if not self.camera.isOpened():
                self.error_occurred.emit("Failed to open camera")
                return False
            
            print("Camera initialized successfully")
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Camera initialization error: {str(e)}")
            return False
    
    def run(self):
        """
        Main detection loop
        """
        if not self.load_model():
            return
        
        if not self.init_camera():
            return
        
        self.running = True
        
        while self.running:
            ret, frame = self.camera.read()
            
            if not ret:
                self.error_occurred.emit("Failed to read frame from camera")
                continue
            
            try:
                results = self.model(
                    frame,
                    conf=config.CONFIDENCE_THRESHOLD,
                    iou=config.IOU_THRESHOLD,
                    verbose=False
                )
                
                detections = []
                annotated_frame = frame.copy()
                
                if len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes
                    
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = float(box.conf[0].cpu().numpy())
                        class_id = int(box.cls[0].cpu().numpy())
                        label = self.model.names[class_id]
                        
                        detections.append({
                            'label': label,
                            'confidence': confidence,
                            'box': (x1, y1, x2, y2),
                            'class_id': class_id
                        })
                        
                        cv2.rectangle(
                            annotated_frame,
                            (int(x1), int(y1)),
                            (int(x2), int(y2)),
                            (0, 255, 0),
                            2
                        )
                        
                        label_text = f"{label} {confidence:.2f}"
                        (text_width, text_height), _ = cv2.getTextSize(
                            label_text,
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            2
                        )
                        
                        cv2.rectangle(
                            annotated_frame,
                            (int(x1), int(y1) - text_height - 10),
                            (int(x1) + text_width, int(y1)),
                            (0, 255, 0),
                            -1
                        )
                        
                        cv2.putText(
                            annotated_frame,
                            label_text,
                            (int(x1), int(y1) - 5),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 0),
                            2
                        )
                
                self.current_detections = detections
                
                rgb_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                self.frame_ready.emit(rgb_frame, detections)
                
                if detections:
                    self.detection_ready.emit(detections)
                
            except Exception as e:
                self.error_occurred.emit(f"Detection error: {str(e)}")
        
        self.cleanup()
    
    def stop(self):
        """
        Stop detection thread
        """
        self.running = False
    
    def cleanup(self):
        """
        Release resources
        """
        if self.camera is not None:
            self.camera.release()
        print("YOLO detector stopped and resources released")
    
    def get_current_detections(self):
        """
        Get current detection results
        """
        return self.current_detections
