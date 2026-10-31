"""
Simple chatbot engine for conversational responses
"""
import random
from datetime import datetime


class ChatbotEngine:
    """
    Simple rule-based chatbot with pattern matching
    Can be extended to use LLM APIs
    """
    
    def __init__(self):
        self.conversation_history = []
        
        # Response patterns
        self.greetings = [
            "Hello! I'm here to help you with object detection.",
            "Hi there! How can I assist you today?",
            "Hey! I'm your Dynabraille assistant.",
        ]
        
        self.help_responses = [
            "I can help you understand what objects are being detected by the camera. Just ask me about any object you see!",
            "This application uses YOLO to detect objects in real-time. The detected objects are displayed in Braille on the right panel.",
            "You can ask me about the detected objects, how Braille works, or anything about the application!",
        ]
        
        self.braille_info = [
            "Braille is a tactile writing system used by people who are blind or visually impaired. Each character is represented by a 3x2 matrix of dots.",
            "The Braille system uses 6 dots arranged in 2 columns of 3 dots each. Different combinations represent different letters and symbols.",
            "In this app, detected object names are converted to Braille and displayed letter by letter on the right panel.",
        ]
        
        self.object_detection_info = [
            "YOLO (You Only Look Once) is a real-time object detection system that can identify 80 different types of objects from the COCO dataset.",
            "The camera feed on the left shows detected objects with bounding boxes and confidence scores.",
            "Common objects like people, cars, phones, cups, and many more can be detected in real-time!",
        ]
        
        self.fallback_responses = [
            "That's interesting! Tell me more.",
            "I see. Is there anything specific you'd like to know about the object detection or Braille display?",
            "I'm here to help with object detection and Braille conversion. What would you like to know?",
            "Interesting question! I'm focused on helping with object detection and Braille display.",
        ]
    
    def get_response(self, user_message):
        """
        Generate a response based on user message
        
        Args:
            user_message: string from user
            
        Returns:
            string response
        """
        message_lower = user_message.lower().strip()
        
        # Store in history
        self.conversation_history.append({
            'user': user_message,
            'timestamp': datetime.now()
        })
        
        # Pattern matching
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'greetings']):
            response = random.choice(self.greetings)
        
        elif any(word in message_lower for word in ['help', 'what can you do', 'assist']):
            response = random.choice(self.help_responses)
        
        elif any(word in message_lower for word in ['braille', 'dots', 'tactile']):
            response = random.choice(self.braille_info)
        
        elif any(word in message_lower for word in ['yolo', 'detect', 'object', 'camera', 'coco']):
            response = random.choice(self.object_detection_info)
        
        elif any(word in message_lower for word in ['thank', 'thanks', 'appreciate']):
            response = "You're welcome! Happy to help!"
        
        elif '?' in message_lower:
            response = random.choice(self.fallback_responses)
        
        else:
            response = random.choice(self.fallback_responses)
        
        # Store response in history
        self.conversation_history[-1]['bot'] = response
        
        return response
    
    def get_history(self):
        """Get conversation history"""
        return self.conversation_history
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
