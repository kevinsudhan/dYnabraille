"""Draws the charts in docs/images/ used by the README.

    server\\.venv\\Scripts\\python docs\\make_charts.py

matplotlib comes with the server's dependencies (ultralytics). The power chart is a
model of the firmware's timing, not a measurement; the latency chart uses numbers
measured on the development PC (see LATENCY below).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent / "images"

# Validated categorical slots (light surface) + text and surface tokens.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.weight": "normal",
    "font.size": 11,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})

# ---------------------------------------------------------------- the cell's layout

# Braille dot d sits under solenoid DOT_TO_SOLENOID[d-1] (firmware config.h).
DOT_TO_SOLENOID = [1, 3, 5, 2, 4, 6]
LETTERS = {"a": {1}, "b": {1, 2}, "c": {1, 4}}

# Firmware 2.3 defaults and dashboard defaults.
CHAR_MS, GAP_MS = 900, 250
PULL_IN_MS, HOLD = 60, 0.5  # one solenoid pulls in at a time, then holds at 50% power
SUPPLY_LIMIT = 3  # measured: the supply can pull down about 3 solenoids at full power


def powered(letter: str) -> list[int]:
    """Solenoids to power for a letter: the ones NOT under a dot (unpowered = pin up)."""
    up = {DOT_TO_SOLENOID[d - 1] for d in LETTERS[letter]}
    return [s for s in range(1, 7) if s not in up]


def timeline(word: str, step: int = 5):
    """Per time step: pins up (set of solenoids) and supply load, old firmware vs 2.3."""
    t, rows = 0, []
    for i, letter in enumerate(word):
        on = powered(letter)
        for ms in range(0, CHAR_MS, step):
            load_new = 0.0
            for k in range(len(on)):
                start = k * PULL_IN_MS
                if ms >= start + PULL_IN_MS:
                    load_new += HOLD
                elif ms >= start:
                    load_new += 1.0
            down = {s for k, s in enumerate(on) if ms >= k * PULL_IN_MS}
            rows.append((t + ms, set(range(1, 7)) - down, len(on), load_new, letter))
        t += CHAR_MS
        if i < len(word) - 1:
            for ms in range(0, GAP_MS, step):
                # old firmware: a blank cell = every solenoid powered; 2.3: everything off
                rows.append((t + ms, set(range(1, 7)), 6, 0.0, None))
            t += GAP_MS
    for ms in range(0, 400, step):
        rows.append((t + ms, set(range(1, 7)), 0, 0.0, None))
    return rows


def power_chart(word: str = "cab") -> None:
    rows = timeline(word)
    times = [r[0] / 1000 for r in rows]
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(10, 6.2), sharex=True, gridspec_kw={"height_ratios": [1, 1.5], "hspace": 0.12})

    # Pins up, one row per solenoid in the cell's own numbering.
    for s in range(1, 7):
        y = 6 - s
        start = None
        for (t, up, *_), x in zip(rows, times):
            if s in up and start is None:
                start = x
            if s not in up and start is not None:
                top.add_patch(FancyBboxPatch((start, y - 0.32), x - start, 0.64, boxstyle="round,pad=0,rounding_size=0.02",
                                             fc=BLUE, ec=SURFACE, lw=1))
                start = None
        if start is not None:
            top.add_patch(FancyBboxPatch((start, y - 0.32), times[-1] - start, 0.64, boxstyle="round,pad=0,rounding_size=0.02",
                                         fc=BLUE, ec=SURFACE, lw=1))
    top.set_ylim(-0.7, 5.7)
    top.set_yticks(range(6), [f"S{s}" for s in range(6, 0, -1)])
    top.tick_params(length=0)
    for spine in top.spines.values():
        spine.set_visible(False)
    top.set_title(f'Spelling "{word}" on the cell (firmware 2.3)', loc="left", fontsize=13, fontweight="bold", pad=26)
    top.text(0, 6.15, "Blue = pin up (solenoid off). Each letter's pins drop one at a time, 60 ms apart; between letters all six rise.",
             color=INK_2, fontsize=10, transform=top.transData)
    t = 0
    for i, letter in enumerate(word):
        top.text((t + CHAR_MS / 2) / 1000, -0.62, f'"{letter}"', ha="center", va="top", color=INK, fontsize=11, fontweight="bold")
        t += CHAR_MS + GAP_MS

    # Supply load in units of "one solenoid at full power".
    old = [r[2] for r in rows]
    new = [r[3] for r in rows]
    bottom.step(times, old, where="post", color=ORANGE, lw=2, label="Before: blank cell between letters (all 6 powered)")
    bottom.step(times, new, where="post", color=BLUE, lw=2, label="Firmware 2.3: staggered pull-in, 50% hold, rest gaps")
    bottom.axhline(SUPPLY_LIMIT, color=INK_2, lw=1.2, ls=(0, (4, 3)))
    bottom.text(0.03, SUPPLY_LIMIT + 0.12, "measured supply limit: about 3 solenoids at full power",
                ha="left", va="bottom", color=INK_2, fontsize=10)
    bottom.set_ylim(0, 8.2)  # headroom above the lines for the legend
    bottom.set_yticks(range(0, 7))
    bottom.set_ylabel("Supply load\n(solenoids at full power)")
    bottom.set_xlabel("Time (s)")
    bottom.grid(axis="y", color=GRID, lw=0.8)
    bottom.set_axisbelow(True)
    for side in ("top", "right"):
        bottom.spines[side].set_visible(False)
    bottom.legend(loc="upper left", frameon=False, fontsize=10, ncols=2, handlelength=1.6)
    bottom.set_xlim(0, times[-1])
    fig.text(0.01, 0.005, "Model of the firmware timing (hold current taken as duty × full current), not a measurement.",
             color=MUTED, fontsize=9)
    fig.savefig(OUT / "power-budget.png", dpi=200, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# ---------------------------------------------------------------- hold-to-talk latency

# Measured 2026-10-31 on the dev PC (Windows, server + ElevenLabs over home broadband),
# from letting go of the button to the start of the spoken reply.
LATENCY = [
    ("Typical press", [("Speech-to-text", 0.59), ("Agent reply", 0.70), ("Voice", 0.60)]),
    ("First press after\nopening the page", [("Speech-to-text", 1.64), ("Agent reply", 0.70), ("Voice", 0.35)]),
]


def latency_chart() -> None:
    colors = {"Speech-to-text": BLUE, "Agent reply": ORANGE, "Voice": AQUA}
    fig, ax = plt.subplots(figsize=(10, 3.1))
    for row, (name, parts) in enumerate(LATENCY):
        y = len(LATENCY) - 1 - row
        left = 0.0
        for part, seconds in parts:
            ax.barh(y, seconds, left=left, height=0.5, color=colors[part], edgecolor=SURFACE, linewidth=2,
                    label=part if row == 0 else None)
            ax.text(left + seconds / 2, y, f"{seconds:.2f} s", ha="center", va="center", color="white",
                    fontsize=10, fontweight="bold")
            left += seconds
        ax.text(left + 0.04, y, f"{left:.1f} s", ha="left", va="center", color=INK, fontsize=11, fontweight="bold")
    ax.set_yticks(range(len(LATENCY)), [name for name, _ in reversed(LATENCY)])
    ax.set_xlim(0, 3.2)
    ax.set_xlabel("Seconds from letting go of Hold to talk until the reply starts playing")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_title("Hold-to-talk response time (measured)", loc="left", fontsize=13, fontweight="bold", pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=3, frameon=False, fontsize=10, handlelength=1.2)
    fig.savefig(OUT / "latency.png", dpi=200, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# ---------------------------------------------------------------- dot vs solenoid numbering

def cell_layout_chart(letter: str = "b") -> None:
    fig, axes = plt.subplots(1, 3, figsize=(10, 4.1))
    positions = {1: (0, 2), 4: (1, 2), 2: (0, 1), 5: (1, 1), 3: (0, 0), 6: (1, 0)}  # braille dot -> (col, row)
    solenoid_at = {(0, 2): 1, (1, 2): 2, (0, 1): 3, (1, 1): 4, (0, 0): 5, (1, 0): 6}
    up = {DOT_TO_SOLENOID[d - 1] for d in LETTERS[letter]}
    panels = [
        ("Braille dot numbers", lambda pos: str(next(d for d, p in positions.items() if p == pos)), lambda pos: False),
        ("Solenoid numbers (row by row)", lambda pos: f"S{solenoid_at[pos]}", lambda pos: False),
        (f'Letter "{letter}": dots 1 and 2', lambda pos: f"S{solenoid_at[pos]}", lambda pos: solenoid_at[pos] in up),
    ]
    for ax, (title, label, raised) in zip(axes, panels):
        ax.add_patch(FancyBboxPatch((-0.55, -0.55), 2.1, 3.1, boxstyle="round,pad=0,rounding_size=0.25", fc="#f1f0ec", ec=GRID))
        for pos in solenoid_at:
            x, y = pos
            last = ax is axes[-1]
            filled = raised(pos)
            ax.add_patch(Circle((x * 1.0, y * 1.0), 0.33, fc=BLUE if filled else SURFACE,
                                ec=BLUE if filled or not last else MUTED, lw=2, ls="-" if filled or not last else (0, (2, 2))))
            ax.text(x, y, label(pos), ha="center", va="center", fontsize=12, fontweight="bold",
                    color="white" if filled else INK)
        ax.set_xlim(-0.8, 1.8)
        ax.set_ylim(-1.1, 2.8)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=11.5, fontweight="bold", color=INK)
    axes[-1].text(0.5, -0.95, "filled = unpowered, pin up (felt)\ndashed = powered, pulled down",
                  ha="center", va="center", fontsize=9.5, color=INK_2)
    fig.suptitle("Dot 1 is under S1, dot 2 under S3, dot 4 under S2 (DOT_TO_SOLENOID = {1, 3, 5, 2, 4, 6})",
                 y=0.04, fontsize=10, color=INK_2)
    fig.savefig(OUT / "cell-layout.png", dpi=200, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    power_chart()
    latency_chart()
    cell_layout_chart()
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.png")) if p.stem in {"power-budget", "latency", "cell-layout"}))
