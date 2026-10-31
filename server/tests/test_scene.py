from dynabraille.scene import Detection, FocusTracker, plural, summarize


def det(label, x1=0.4, y1=0.3, x2=0.6, y2=0.7, conf=0.9):
    return Detection(label, conf, (x1, y1, x2, y2))


def test_plural():
    assert plural("person", 3) == "people"
    assert plural("bus", 2) == "buses"
    assert plural("cell phone", 2) == "cell phones"
    assert plural("chair", 1) == "chair"


def test_position_and_distance():
    assert det("cup", 0.0, 0.4, 0.2, 0.5).position == "left"
    assert det("cup", 0.8, 0.4, 1.0, 0.5).position == "right"
    assert det("person", 0.2, 0.05, 0.8, 0.95).distance == "very close"
    assert det("cup", 0.45, 0.45, 0.5, 0.5).distance == "further away"


def test_summary_mentions_counts_and_nearest():
    text = summarize([det("person"), det("person", 0.0, 0.4, 0.1, 0.5), det("chair", 0.7, 0.6, 0.8, 0.7)])
    assert text.startswith("I can see 2 people and a chair.")
    assert "The nearest is a person ahead of you" in text
    assert summarize([]).startswith("I don't see")


def test_focus_needs_to_be_stable():
    tracker = FocusTracker(stable_ms=500)
    assert tracker.update([det("cup")], now=0.0) is None
    assert tracker.update([det("cup")], now=0.3) is None
    changed = tracker.update([det("cup")], now=0.6)
    assert changed and changed.label == "cup"
    assert tracker.update([det("cup")], now=0.7) is None  # same object: no new event
    # something else briefly filling the view doesn't steal focus
    assert tracker.update([det("dog", 0.1, 0.1, 0.9, 0.9)], now=0.8) is None
    assert tracker.update([det("cup")], now=0.9) is None
    assert tracker.current.label == "cup"


def test_focus_clears_after_empty_frames():
    tracker = FocusTracker(stable_ms=0, clear_after_ms=1000)
    tracker.update([det("cup")], now=0.0)
    tracker.update([], now=0.5)
    assert tracker.current is not None
    tracker.update([], now=1.6)
    assert tracker.current is None
