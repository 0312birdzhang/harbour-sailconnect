#!/usr/bin/env python3
"""Export the transparent cover illustration from its editable SVG source."""
from pathlib import Path
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/images/cover-sailconnect.svg"

if __name__ == "__main__":
    cairosvg.svg2png(url=str(SOURCE),
                    write_to=str(SOURCE.with_suffix(".png")),
                    output_width=1080, output_height=780)
