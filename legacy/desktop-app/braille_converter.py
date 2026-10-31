"""
Braille character converter - ASCII to 3x2 Braille dot matrix
Based on 6-dot Braille standard (dots numbered 1-6)
"""


class BrailleConverter:
    """
    Converts ASCII characters to 3x2 Braille dot patterns
    Dot numbering:
    1 4
    2 5
    3 6
    """
    
    # Braille ASCII mapping (simplified for common characters)
    # Each character maps to a list of raised dots (1-6)
    BRAILLE_MAP = {
        'a': [1],
        'b': [1, 2],
        'c': [1, 4],
        'd': [1, 4, 5],
        'e': [1, 5],
        'f': [1, 2, 4],
        'g': [1, 2, 4, 5],
        'h': [1, 2, 5],
        'i': [2, 4],
        'j': [2, 4, 5],
        'k': [1, 3],
        'l': [1, 2, 3],
        'm': [1, 3, 4],
        'n': [1, 3, 4, 5],
        'o': [1, 3, 5],
        'p': [1, 2, 3, 4],
        'q': [1, 2, 3, 4, 5],
        'r': [1, 2, 3, 5],
        's': [2, 3, 4],
        't': [2, 3, 4, 5],
        'u': [1, 3, 6],
        'v': [1, 2, 3, 6],
        'w': [2, 4, 5, 6],
        'x': [1, 3, 4, 6],
        'y': [1, 3, 4, 5, 6],
        'z': [1, 3, 5, 6],
        '0': [3, 5, 6],
        '1': [2],
        '2': [2, 3],
        '3': [2, 5],
        '4': [2, 5, 6],
        '5': [2, 6],
        '6': [2, 3, 5],
        '7': [2, 3, 5, 6],
        '8': [2, 3, 6],
        '9': [3, 5],
        ' ': [],  # Space - no dots
        '.': [4, 6],
        ',': [6],
        '!': [2, 3, 4, 6],
        '?': [1, 4, 5, 6],
        '-': [3, 6],
        '_': [4, 5, 6],
    }
    
    @staticmethod
    def char_to_dots(char):
        """
        Convert a single character to Braille dot pattern
        
        Args:
            char: single character string
            
        Returns:
            list of raised dot numbers (1-6), or empty list if not found
        """
        char_lower = char.lower()
        return BrailleConverter.BRAILLE_MAP.get(char_lower, [])
    
    @staticmethod
    def text_to_braille(text):
        """
        Convert text string to list of Braille dot patterns
        
        Args:
            text: string to convert
            
        Returns:
            list of tuples (char, dots) where dots is list of raised dot numbers
        """
        result = []
        for char in text:
            dots = BrailleConverter.char_to_dots(char)
            result.append((char, dots))
        return result
    
    @staticmethod
    def dots_to_matrix(dots):
        """
        Convert dot numbers to 3x2 boolean matrix
        
        Args:
            dots: list of raised dot numbers (1-6)
            
        Returns:
            3x2 list of lists, True for raised, False for lowered
        """
        # Initialize 3x2 matrix (3 rows, 2 columns)
        matrix = [[False, False],
                  [False, False],
                  [False, False]]
        
        # Map dot numbers to matrix positions
        dot_positions = {
            1: (0, 0),  # Row 0, Col 0
            2: (1, 0),  # Row 1, Col 0
            3: (2, 0),  # Row 2, Col 0
            4: (0, 1),  # Row 0, Col 1
            5: (1, 1),  # Row 1, Col 1
            6: (2, 1),  # Row 2, Col 1
        }
        
        # Set raised dots
        for dot in dots:
            if dot in dot_positions:
                row, col = dot_positions[dot]
                matrix[row][col] = True
        
        return matrix
    
    @staticmethod
    def get_braille_unicode(dots):
        """
        Get Unicode Braille character for given dots
        
        Args:
            dots: list of raised dot numbers (1-6)
            
        Returns:
            Unicode Braille character
        """
        # Unicode Braille patterns start at U+2800
        # Each dot adds a specific value
        dot_values = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32, 7: 64, 8: 128}
        
        value = sum(dot_values.get(dot, 0) for dot in dots)
        return chr(0x2800 + value)
