from dynabraille.braille import dots_to_mask, encode, mask_to_dots, to_unicode


def masks(text):
    return [c.mask for c in encode(text)]


def test_mask_roundtrip():
    for dots in ([], [1], [1, 2, 3, 4, 5, 6], [2, 5]):
        assert mask_to_dots(dots_to_mask(dots)) == dots


def test_letters_match_unicode_braille():
    assert to_unicode("person") == "⠏⠑⠗⠎⠕⠝"
    assert to_unicode("abcdefghijklmnopqrstuvwxyz") == "⠁⠃⠉⠙⠑⠋⠛⠓⠊⠚⠅⠇⠍⠝⠕⠏⠟⠗⠎⠞⠥⠧⠺⠭⠽⠵"


def test_numbers_use_number_sign_and_letter_sign():
    assert to_unicode("42") == "⠼⠙⠃"
    assert to_unicode("2b") == "⠼⠃⠰⠃"  # a-j right after a digit needs the letter sign
    assert to_unicode("3.5") == "⠼⠉⠲⠑"
    assert to_unicode("2 cups") == "⠼⠃⠀⠉⠥⠏⠎"


def test_capitals():
    assert to_unicode("Cup") == "⠠⠉⠥⠏"
    assert to_unicode("TV") == "⠠⠠⠞⠧"


def test_punctuation_and_spacing():
    assert to_unicode("hi, you!") == "⠓⠊⠂⠀⠽⠕⠥⠖"
    assert to_unicode("  stop.  ") == "⠎⠞⠕⠏⠲"
    assert to_unicode('"ok"') == "⠦⠕⠅⠴"


def test_unknown_characters_are_skipped_and_length_capped():
    assert masks("a~b") == masks("ab")
    assert len(encode("a" * 1000, max_cells=50)) == 50
