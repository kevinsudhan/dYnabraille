"""
Test script for ESP32 controller
Tests serial communication and solenoid commands
"""
import time
from esp32_controller import ESP32Controller


def test_connection():
    """Test ESP32 connection"""
    print("Testing ESP32 Connection...")
    print("-" * 50)
    
    controller = ESP32Controller()
    
    if controller.connect():
        print("✓ Connection successful")
        
        status = controller.get_status()
        print(f"Status: {status}")
        
        controller.disconnect()
        return True
    else:
        print("✗ Connection failed")
        return False


def test_braille_patterns():
    """Test sending Braille patterns"""
    print("\nTesting Braille Patterns...")
    print("-" * 50)
    
    controller = ESP32Controller()
    
    if not controller.connect():
        print("Cannot connect to ESP32")
        return
    
    patterns = [
        ([1], "Letter A"),
        ([1, 2], "Letter B"),
        ([1, 4], "Letter C"),
        ([1, 2, 3, 4, 5, 6], "All dots"),
        ([], "No dots (space)"),
    ]
    
    for dots, description in patterns:
        print(f"\nSending: {description}")
        print(f"Dots: {dots}")
        
        success = controller.send_braille_pattern(dots)
        
        if success:
            print("✓ Pattern sent")
        else:
            print("✗ Failed to send")
        
        time.sleep(2)
    
    controller.reset_solenoids()
    print("\n✓ Reset solenoids")
    
    controller.disconnect()


def test_character_sequence():
    """Test sending character sequence"""
    print("\nTesting Character Sequence...")
    print("-" * 50)
    
    controller = ESP32Controller()
    
    if not controller.connect():
        print("Cannot connect to ESP32")
        return
    
    word = "hello"
    
    from braille_converter import BrailleConverter
    converter = BrailleConverter()
    
    braille_chars = converter.text_to_braille(word)
    
    print(f"Displaying word: {word.upper()}")
    
    for char, dots in braille_chars:
        print(f"\nCharacter: {char.upper()}")
        print(f"Dots: {dots}")
        
        controller.send_character(char, dots)
        time.sleep(1)
    
    time.sleep(2)
    controller.reset_solenoids()
    
    controller.disconnect()
    print("\n✓ Sequence complete")


def test_rapid_updates():
    """Test rapid pattern updates"""
    print("\nTesting Rapid Updates...")
    print("-" * 50)
    
    controller = ESP32Controller()
    
    if not controller.connect():
        print("Cannot connect to ESP32")
        return
    
    patterns = [
        [1], [2], [3], [4], [5], [6],
        [1, 4], [2, 5], [3, 6],
        []
    ]
    
    print("Sending rapid pattern sequence...")
    
    for i, dots in enumerate(patterns):
        controller.send_braille_pattern(dots)
        print(f"Pattern {i+1}/{len(patterns)}: {dots}")
        time.sleep(0.3)
    
    controller.reset_solenoids()
    controller.disconnect()
    print("\n✓ Rapid update test complete")


if __name__ == '__main__':
    print("ESP32 Controller Test Suite")
    print("=" * 50)
    
    if test_connection():
        choice = input("\nRun full test suite? (y/n): ")
        
        if choice.lower() == 'y':
            test_braille_patterns()
            test_character_sequence()
            test_rapid_updates()
            
            print("\n" + "=" * 50)
            print("All tests completed!")
    else:
        print("\nPlease check ESP32 connection and try again")
