"""
Test script for Braille converter
Validates ASCII to Braille dot pattern conversion
"""
from braille_converter import BrailleConverter


def test_basic_characters():
    """Test basic alphabet conversion"""
    print("Testing Basic Characters:")
    print("-" * 50)
    
    test_chars = ['a', 'b', 'c', 'h', 'e', 'l', 'o']
    
    for char in test_chars:
        dots = BrailleConverter.char_to_dots(char)
        matrix = BrailleConverter.dots_to_matrix(dots)
        unicode_char = BrailleConverter.get_braille_unicode(dots)
        
        print(f"\nCharacter: {char.upper()}")
        print(f"Dots: {dots}")
        print(f"Unicode: {unicode_char}")
        print("Matrix:")
        for row in matrix:
            print(f"  {['●' if cell else '○' for cell in row]}")


def test_word_conversion():
    """Test full word conversion"""
    print("\n\nTesting Word Conversion:")
    print("-" * 50)
    
    words = ["hello", "cup", "person", "phone"]
    
    for word in words:
        print(f"\nWord: {word.upper()}")
        braille_chars = BrailleConverter.text_to_braille(word)
        
        unicode_str = ""
        for char, dots in braille_chars:
            unicode_str += BrailleConverter.get_braille_unicode(dots)
        
        print(f"Braille: {unicode_str}")
        print(f"Characters: {len(braille_chars)}")


def test_numbers():
    """Test number conversion"""
    print("\n\nTesting Numbers:")
    print("-" * 50)
    
    for num in range(10):
        char = str(num)
        dots = BrailleConverter.char_to_dots(char)
        unicode_char = BrailleConverter.get_braille_unicode(dots)
        
        print(f"{char}: {dots} → {unicode_char}")


def test_special_characters():
    """Test special character conversion"""
    print("\n\nTesting Special Characters:")
    print("-" * 50)
    
    special = [' ', '.', ',', '!', '?', '-']
    
    for char in special:
        dots = BrailleConverter.char_to_dots(char)
        unicode_char = BrailleConverter.get_braille_unicode(dots)
        
        char_display = 'SPACE' if char == ' ' else char
        print(f"{char_display}: {dots} → {unicode_char}")


if __name__ == '__main__':
    test_basic_characters()
    test_word_conversion()
    test_numbers()
    test_special_characters()
    
    print("\n" + "=" * 50)
    print("All tests completed!")
