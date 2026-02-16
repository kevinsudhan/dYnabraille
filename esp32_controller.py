"""
ESP32 Communication Module for Braille Solenoid Control
Handles serial communication with ESP32 microcontroller
"""
import serial
import serial.tools.list_ports
import json
import time
from threading import Thread, Lock


class ESP32Controller:
    """
    Manages communication with ESP32 for controlling Braille solenoids
    """
    
    def __init__(self, baudrate=115200, timeout=1):
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_port = None
        self.is_connected = False
        self.lock = Lock()
        self.auto_reconnect = True
        
    def find_esp32_port(self):
        """
        Automatically detect ESP32 COM port
        
        Returns:
            str: COM port name or None
        """
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if 'CP210' in port.description or 'CH340' in port.description or 'USB' in port.description:
                return port.device
        return None
    
    def connect(self, port=None):
        """
        Connect to ESP32 via serial port
        
        Args:
            port: COM port name (auto-detect if None)
            
        Returns:
            bool: Connection success
        """
        try:
            if port is None:
                port = self.find_esp32_port()
                
            if port is None:
                print("No ESP32 device found")
                return False
            
            with self.lock:
                self.serial_port = serial.Serial(
                    port=port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.timeout
                )
                time.sleep(2)
                self.is_connected = True
                print(f"Connected to ESP32 on {port}")
                return True
                
        except serial.SerialException as e:
            print(f"Failed to connect to ESP32: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """
        Disconnect from ESP32
        """
        with self.lock:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                self.is_connected = False
                print("Disconnected from ESP32")
    
    def send_braille_pattern(self, dots):
        """
        Send Braille dot pattern to ESP32 for solenoid actuation
        
        Args:
            dots: list of raised dot numbers (1-6)
            
        Returns:
            bool: Send success
        """
        if not self.is_connected:
            return False
        
        try:
            command = {
                'type': 'braille',
                'dots': dots,
                'timestamp': int(time.time() * 1000)
            }
            
            message = json.dumps(command) + '\n'
            
            with self.lock:
                self.serial_port.write(message.encode('utf-8'))
                self.serial_port.flush()
            
            return True
            
        except Exception as e:
            print(f"Error sending Braille pattern: {e}")
            return False
    
    def send_character(self, char, dots):
        """
        Send character and its Braille pattern to ESP32
        
        Args:
            char: character being displayed
            dots: list of raised dot numbers
            
        Returns:
            bool: Send success
        """
        if not self.is_connected:
            return False
        
        try:
            command = {
                'type': 'character',
                'char': char,
                'dots': dots,
                'timestamp': int(time.time() * 1000)
            }
            
            message = json.dumps(command) + '\n'
            
            with self.lock:
                self.serial_port.write(message.encode('utf-8'))
                self.serial_port.flush()
            
            return True
            
        except Exception as e:
            print(f"Error sending character: {e}")
            return False
    
    def reset_solenoids(self):
        """
        Reset all solenoids to lowered position
        
        Returns:
            bool: Send success
        """
        if not self.is_connected:
            return False
        
        try:
            command = {
                'type': 'reset',
                'timestamp': int(time.time() * 1000)
            }
            
            message = json.dumps(command) + '\n'
            
            with self.lock:
                self.serial_port.write(message.encode('utf-8'))
                self.serial_port.flush()
            
            return True
            
        except Exception as e:
            print(f"Error resetting solenoids: {e}")
            return False
    
    def read_response(self):
        """
        Read response from ESP32
        
        Returns:
            dict: Parsed JSON response or None
        """
        if not self.is_connected:
            return None
        
        try:
            with self.lock:
                if self.serial_port.in_waiting > 0:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    if line:
                        return json.loads(line)
            return None
            
        except Exception as e:
            print(f"Error reading response: {e}")
            return None
    
    def get_status(self):
        """
        Get ESP32 status
        
        Returns:
            dict: Status information
        """
        if not self.is_connected:
            return {'connected': False}
        
        try:
            command = {
                'type': 'status',
                'timestamp': int(time.time() * 1000)
            }
            
            message = json.dumps(command) + '\n'
            
            with self.lock:
                self.serial_port.write(message.encode('utf-8'))
                self.serial_port.flush()
            
            time.sleep(0.1)
            response = self.read_response()
            
            if response:
                return response
            else:
                return {'connected': True, 'status': 'no_response'}
                
        except Exception as e:
            print(f"Error getting status: {e}")
            return {'connected': False, 'error': str(e)}
