"""Turns raw detections into something a person can use.

* picks a single "focus" object (closest, most central) and only changes it once
  the new choice has been stable for a moment, so the braille cell doesn't flicker;
* describes the scene in a short sentence for speech and for the AI assistant.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

# Short words are much quicker to read on a single braille cell.
BRAILLE_ALIASES = {
    "cell phone": "phone",
    "dining table": "table",
    "potted plant": "plant",
    "sports ball": "ball",
    "traffic light": "signal",
    "fire hydrant": "hydrant",
    "parking meter": "meter",
    "wine glass": "glass",
    "teddy bear": "teddy",
    "hair drier": "dryer",
    "baseball bat": "bat",
    "baseball glove": "glove",
    "tennis racket": "racket",
    "motorcycle": "bike",
    "bicycle": "cycle",
    "refrigerator": "fridge",
    "airplane": "plane",
}

_IRREGULAR = {"person": "people", "knife": "knives", "mouse": "mice", "sheep": "sheep",
              "skis": "skis", "scissors": "scissors"}


def plural(label: str, n: int) -> str:
    if n == 1:
        return label
    head, _, last = label.rpartition(" ")
    if last in _IRREGULAR:
        word = _IRREGULAR[last]
    elif last.endswith(("s", "sh", "ch", "x")):
        word = last + "es"
    else:
        word = last + "s"
    return f"{head} {word}" if head else word


def with_article(label: str) -> str:
    return ("an " if label[0] in "aeiou" else "a ") + label


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2, normalised 0..1

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    @property
    def position(self) -> str:
        cx = (self.box[0] + self.box[2]) / 2
        return "left" if cx < 0.36 else "right" if cx > 0.64 else "ahead"

    @property
    def distance(self) -> str:
        # A rough cue from how much of the frame the object fills.
        height = self.box[3] - self.box[1]
        if height > 0.7 or self.area > 0.35:
            return "very close"
        if height > 0.4 or self.area > 0.12:
            return "close"
        return "further away"

    @property
    def braille_word(self) -> str:
        return BRAILLE_ALIASES.get(self.label, self.label)

    def describe(self) -> str:
        where = "ahead of you" if self.position == "ahead" else f"on your {self.position}"
        return f"{with_article(self.label)} {where}, {self.distance}"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "box": [round(v, 4) for v in self.box],
            "position": self.position,
            "distance": self.distance,
        }

    def focus_score(self) -> float:
        centre = 1.0 if self.position == "ahead" else 0.7
        return self.area * centre * (0.5 + self.confidence)


def summarize(detections: list[Detection]) -> str:
    if not detections:
        return "I don't see any objects I recognise right now."
    counts = Counter(d.label for d in detections)
    parts = [f"{n} {plural(label, n)}" if n > 1 else with_article(label)
             for label, n in counts.most_common(6)]
    listing = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    nearest = max(detections, key=Detection.focus_score)
    return f"I can see {listing}. The nearest is {nearest.describe()}."


def braille_listing(detections: list[Detection], limit: int = 5) -> str:
    """Short text for the braille cell, nearest first: "bus, 4 people"."""
    if not detections:
        return "none"
    counts = Counter(d.braille_word for d in sorted(detections, key=Detection.focus_score, reverse=True))
    return ", ".join(f"{n} {plural(word, n)}" if n > 1 else word
                     for word, n in list(counts.items())[:limit])


@dataclass
class FocusTracker:
    """Debounces the focus object so braille output only changes on a real change."""

    stable_ms: int = 700
    clear_after_ms: int = 2500
    current: Detection | None = None
    _candidate: str | None = None
    _candidate_since: float = 0.0
    _last_seen: float = field(default_factory=time.monotonic)

    def update(self, detections: list[Detection], now: float | None = None) -> Detection | None:
        """Feed one frame. Returns the new focus when it changes, else None."""
        now = time.monotonic() if now is None else now
        if not detections:
            if self.current and (now - self._last_seen) * 1000 > self.clear_after_ms:
                self.current = None
                self._candidate = None
            return None

        self._last_seen = now
        best = max(detections, key=Detection.focus_score)
        if self.current and best.label == self.current.label:
            self.current = best  # same object, refresh its box
            self._candidate = None
            return None

        if best.label != self._candidate:
            self._candidate = best.label
            self._candidate_since = now
        if (now - self._candidate_since) * 1000 >= self.stable_ms:
            self.current = best
            self._candidate = None
            return best
        return None
