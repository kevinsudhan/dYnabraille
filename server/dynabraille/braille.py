"""Text to 6-dot braille cells (Unified English Braille, grade 1 / uncontracted).

A cell is a 6-bit mask: bit 0 is dot 1 ... bit 5 is dot 6, which is also the
offset into the Unicode braille block (U+2800), so chr(0x2800 + mask) renders it.

    1 4
    2 5
    3 6
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


def dots_to_mask(dots: list[int] | tuple[int, ...]) -> int:
    mask = 0
    for d in dots:
        if 1 <= d <= 6:
            mask |= 1 << (d - 1)
    return mask


def mask_to_dots(mask: int) -> list[int]:
    return [d for d in range(1, 7) if mask & (1 << (d - 1))]


def _m(*dots: int) -> int:
    return dots_to_mask(dots)


LETTERS = {
    "a": _m(1), "b": _m(1, 2), "c": _m(1, 4), "d": _m(1, 4, 5), "e": _m(1, 5),
    "f": _m(1, 2, 4), "g": _m(1, 2, 4, 5), "h": _m(1, 2, 5), "i": _m(2, 4), "j": _m(2, 4, 5),
    "k": _m(1, 3), "l": _m(1, 2, 3), "m": _m(1, 3, 4), "n": _m(1, 3, 4, 5), "o": _m(1, 3, 5),
    "p": _m(1, 2, 3, 4), "q": _m(1, 2, 3, 4, 5), "r": _m(1, 2, 3, 5), "s": _m(2, 3, 4),
    "t": _m(2, 3, 4, 5), "u": _m(1, 3, 6), "v": _m(1, 2, 3, 6), "w": _m(2, 4, 5, 6),
    "x": _m(1, 3, 4, 6), "y": _m(1, 3, 4, 5, 6), "z": _m(1, 3, 5, 6),
}
# Digits are the letters a-j after a number sign.
DIGITS = {str((i + 1) % 10): LETTERS[ch] for i, ch in enumerate("abcdefghij")}

CAPITAL = _m(6)
NUMBER = _m(3, 4, 5, 6)
GRADE1 = _m(5, 6)  # letter sign: "the next a-j is a letter, not a digit"

PUNCTUATION: dict[str, tuple[int, ...]] = {
    ",": (_m(2),),
    ";": (_m(2, 3),),
    ":": (_m(2, 5),),
    ".": (_m(2, 5, 6),),
    "!": (_m(2, 3, 5),),
    "?": (_m(2, 3, 6),),
    "'": (_m(3),),
    "-": (_m(3, 6),),
    "(": (_m(5), _m(1, 2, 6)),
    ")": (_m(5), _m(3, 4, 5)),
    "/": (_m(4, 5, 6), _m(3, 4)),
    "@": (_m(4), _m(1)),
    "&": (_m(4), _m(1, 2, 3, 4, 6)),
    "+": (_m(5), _m(2, 3, 5)),
    "=": (_m(5), _m(2, 3, 5, 6)),
    "*": (_m(5), _m(3, 5)),
    "#": (_m(4, 5, 6), _m(1, 4, 5, 6)),
    "%": (_m(4, 6), _m(3, 5, 6)),
    "$": (_m(4), _m(2, 3, 4)),
}
OPEN_QUOTE = _m(2, 3, 6)
CLOSE_QUOTE = _m(3, 5, 6)


@dataclass(frozen=True)
class Cell:
    char: str  # what this cell stands for, e.g. "p", "3", "⠠" for an indicator
    mask: int
    kind: str  # letter | digit | indicator | punct | space

    @property
    def unicode(self) -> str:
        return chr(0x2800 + self.mask)

    def to_dict(self) -> dict:
        return asdict(self) | {"unicode": self.unicode, "dots": mask_to_dots(self.mask)}


def encode(text: str, max_cells: int = 200) -> list[Cell]:
    """Encode text as uncontracted UEB. Unknown characters are skipped."""
    cells: list[Cell] = []
    numeric = False
    quote_open = False
    text = " ".join(text.split())  # collapse newlines / runs of whitespace
    i = 0
    while i < len(text):
        ch = text[i]
        low = ch.lower()

        if ch.isdigit():
            if not numeric:
                cells.append(Cell("#", NUMBER, "indicator"))
                numeric = True
            cells.append(Cell(ch, DIGITS[ch], "digit"))
        elif low in LETTERS:
            if numeric and low in "abcdefghij":
                cells.append(Cell(";", GRADE1, "indicator"))
            numeric = False
            word_end = i
            while word_end < len(text) and text[word_end].isalpha():
                word_end += 1
            word = text[i:word_end]
            if len(word) > 1 and word.isupper() and word.isascii():
                cells.append(Cell("^^", CAPITAL, "indicator"))
                cells.append(Cell("^^", CAPITAL, "indicator"))
                cells.extend(Cell(c.lower(), LETTERS[c.lower()], "letter") for c in word)
                i = word_end
                continue
            if ch.isupper():
                cells.append(Cell("^", CAPITAL, "indicator"))
            cells.append(Cell(low, LETTERS[low], "letter"))
        elif ch == " ":
            numeric = False
            if cells and cells[-1].kind != "space":
                cells.append(Cell(" ", 0, "space"))
        elif ch in ".," and numeric and i + 1 < len(text) and text[i + 1].isdigit():
            cells.append(Cell(ch, PUNCTUATION[ch][0], "punct"))  # 3.5, 1,000 stay numeric
        elif ch == '"':
            numeric = False
            cells.append(Cell(ch, CLOSE_QUOTE if quote_open else OPEN_QUOTE, "punct"))
            quote_open = not quote_open
        elif ch in PUNCTUATION:
            numeric = False
            cells.extend(Cell(ch, m, "punct") for m in PUNCTUATION[ch])
        i += 1

    while cells and cells[-1].kind == "space":
        cells.pop()
    return cells[:max_cells]


def to_unicode(text: str) -> str:
    return "".join(c.unicode for c in encode(text))
