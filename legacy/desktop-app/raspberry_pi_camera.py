"""
Raspberry Pi Camera Module
Handles video streaming from Raspberry Pi camera over network
"""
import cv2
import numpy as np
import socket
import struct
import pickle
from threading import Thread, Lock
from PyQt5.QtCore import QThread, pyqtSignal


class RaspberryPiCamera(QThread):
    """
    Receives video stream from Raspberry Pi camera over network
    """
    
    frame_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, pi_host='raspberrypi.local', pi_port=8000):
        super().__init__()
        self.pi_host = pi_host
        self.pi_port = pi_port
        self.running = False
        self.socket = None
        self.lock = Lock()
        
    def connect_to_pi(self):
        """
        Connect to Raspberry Pi camera server
        
        Returns:
            bool: Connection success
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.pi_host, self.pi_port))
            print(f"Connected to Raspberry Pi at {self.pi_host}:{self.pi_port}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"Failed to connect to Raspberry Pi: {str(e)}")
            return False
    
    def run(self):
        """
        Main receiving loop
        """
        if not self.connect_to_pi():
            return
        
        self.running = True
        data = b""
        payload_size = struct.calcsize("Q")
        
        while self.running:
            try:
                while len(data) < payload_size:
                    packet = self.socket.recv(4096)
                    if not packet:
                        break
                    data += packet
                
                if len(data) < payload_size:
                    break
                
                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("Q", packed_msg_size)[0]
                
                while len(data) < msg_size:
                    data += self.socket.recv(4096)
                
                frame_data = data[:msg_size]
                data = data[msg_size:]
                
                frame = pickle.loads(frame_data)
                
                self.frame_ready.emit(frame)
                
            except Exception as e:
                self.error_occurred.emit(f"Error receiving frame: {str(e)}")
                break
        
        self.cleanup()
    
    def stop(self):
        """
        Stop receiving thread
        """
        self.running = False
    
    def cleanup(self):
        """
        Close connection
        """
        if self.socket:
            self.socket.close()
        print("Raspberry Pi camera connection closed")


class LocalCameraWithPiFallback:
    """
    Camera manager that tries local camera first, falls back to Raspberry Pi
    """
    
    def __init__(self, local_index=0, pi_host='raspberrypi.local', pi_port=8000):
        self.local_index = local_index
        self.pi_host = pi_host
        self.pi_port = pi_port
        self.using_pi = False
        self.camera = None
        self.pi_camera = None
        
    def initialize(self):
        """
        Initialize camera (local or Pi)
        
        Returns:
            bool: Success status
        """
        self.camera = cv2.VideoCapture(self.local_index)
        
        if self.camera.isOpened():
            print("Using local camera")
            self.using_pi = False
            return True
        else:
            print("Local camera not available, trying Raspberry Pi...")
            self.camera.release()
            self.camera = None
            
            self.pi_camera = RaspberryPiCamera(self.pi_host, self.pi_port)
            self.using_pi = True
            return True
    
    def read(self):
        """
        Read frame from active camera
        
        Returns:
            tuple: (success, frame)
        """
        if self.using_pi and self.pi_camera:
            return False, None
        elif self.camera:
            return self.camera.read()
        return False, None
    
    def release(self):
        """
        Release camera resources
        """
        if self.camera:
            self.camera.release()
        if self.pi_camera:
            self.pi_camera.stop()
