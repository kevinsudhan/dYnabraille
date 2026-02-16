"""
Raspberry Pi Camera Server
Run this script on Raspberry Pi to stream camera feed to main application
"""
import socket
import struct
import pickle
import cv2
import time


class PiCameraServer:
    """
    Streams Raspberry Pi camera feed over network
    """
    
    def __init__(self, host='0.0.0.0', port=8000, resolution=(640, 480), fps=30):
        self.host = host
        self.port = port
        self.resolution = resolution
        self.fps = fps
        self.server_socket = None
        self.camera = None
        
    def initialize_camera(self):
        """
        Initialize Pi camera
        """
        try:
            from picamera2 import Picamera2
            
            self.camera = Picamera2()
            config = self.camera.create_preview_configuration(
                main={"size": self.resolution, "format": "RGB888"}
            )
            self.camera.configure(config)
            self.camera.start()
            print("Picamera2 initialized")
            return True
            
        except ImportError:
            print("Picamera2 not available, using OpenCV")
            self.camera = cv2.VideoCapture(0)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.camera.set(cv2.CAP_PROP_FPS, self.fps)
            
            if not self.camera.isOpened():
                print("Failed to open camera")
                return False
            
            print("OpenCV camera initialized")
            return True
    
    def start_server(self):
        """
        Start streaming server
        """
        if not self.initialize_camera():
            return
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        print(f"Camera server started on {self.host}:{self.port}")
        print("Waiting for connection...")
        
        while True:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"Client connected: {addr}")
                
                self.stream_to_client(client_socket)
                
            except KeyboardInterrupt:
                print("\nShutting down server...")
                break
            except Exception as e:
                print(f"Error: {e}")
        
        self.cleanup()
    
    def stream_to_client(self, client_socket):
        """
        Stream frames to connected client
        
        Args:
            client_socket: connected client socket
        """
        try:
            while True:
                if hasattr(self.camera, 'capture_array'):
                    frame = self.camera.capture_array()
                else:
                    ret, frame = self.camera.read()
                    if not ret:
                        break
                
                data = pickle.dumps(frame)
                message_size = struct.pack("Q", len(data))
                
                client_socket.sendall(message_size + data)
                
                time.sleep(1.0 / self.fps)
                
        except Exception as e:
            print(f"Streaming error: {e}")
        finally:
            client_socket.close()
            print("Client disconnected")
    
    def cleanup(self):
        """
        Clean up resources
        """
        if self.camera:
            if hasattr(self.camera, 'stop'):
                self.camera.stop()
            elif hasattr(self.camera, 'release'):
                self.camera.release()
        
        if self.server_socket:
            self.server_socket.close()
        
        print("Server stopped")


def main():
    """
    Main entry point for Pi camera server
    """
    server = PiCameraServer(
        host='0.0.0.0',
        port=8000,
        resolution=(640, 480),
        fps=30
    )
    
    server.start_server()


if __name__ == '__main__':
    main()
