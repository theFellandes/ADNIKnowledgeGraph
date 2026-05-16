"""Shared matplotlib styling for the figures package.

Two palettes:
  - "thesis"  → GSU institutional colours (dark blue, pink accent, yellow)
  - "paper"   → greyscale-friendly for the journal print copy

Use::

    import matplotlib.pyplot as plt
    from figures._style import apply_style, PALETTES

    apply_style("thesis")
    fig, ax = plt.subplots()
    ax.bar(x, y, color=PALETTES["thesis"]["primary"])
"""

from __future__ import annotations

from typing import Any

# GSU institutional palette (per IMPLEMENTATION_PLAN.md §7)
PALETTES: dict[str, dict[str, str]] = {
    "thesis": {
        "primary":   "#184A7C",  # GSU dark blue
        "accent":    "#B5397D",  # GSU pink
        "secondary": "#B8B90C",  # GSU yellow
        "neutral":   "#4A4A4A",
        "muted":     "#9CA3AF",
        "good":      "#15803D",
        "bad":       "#B91C1C",
        "background": "#FFFFFF",
    },
    "paper": {
        "primary":   "#1F2937",
        "accent":    "#525252",
        "secondary": "#737373",
        "neutral":   "#0F172A",
        "muted":     "#A3A3A3",
        "good":      "#404040",
        "bad":       "#171717",
        "background": "#FFFFFF",
    },
}


def apply_style(palette_name: str = "thesis") -> dict[str, Any]:
    """Apply seaborn-v0_8-whitegrid + the chosen palette to matplotlib's rcParams.

    Returns the palette dict so callers can reach for specific colours.
    Imports matplotlib lazily so the figures package is importable in
    environments without matplotlib (e.g., quick unit-test runs).
    """

    import matplotlib.pyplot as plt

    palette = PALETTES.get(palette_name, PALETTES["thesis"])
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "axes.edgecolor": palette["neutral"],
            "axes.labelcolor": palette["neutral"],
            "xtick.color": palette["neutral"],
            "ytick.color": palette["neutral"],
            "axes.titleweight": "bold",
            "font.family": "DejaVu Sans",
            "savefig.bbox": "tight",
            "savefig.dpi": 200,
        }
    )
    return palette
