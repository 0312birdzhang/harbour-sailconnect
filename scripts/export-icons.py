#!/usr/bin/env python3
"""Render the launcher SVG into Sailfish launcher sizes and a large preview.

Requires CairoSVG: python3 -m pip install CairoSVG
"""

from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "rpm" / "harbour-sailconnect.svg"


def main():
    for size in (86, 108, 128, 172):
        destination = ROOT / "rpm" / "icons" / f"{size}x{size}" / "harbour-sailconnect.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(url=str(SOURCE), write_to=str(destination),
                        output_width=size, output_height=size)

    preview = ROOT / "design" / "harbour-sailconnect.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(url=str(SOURCE), write_to=str(preview),
                    output_width=512, output_height=512)


if __name__ == "__main__":
    main()
