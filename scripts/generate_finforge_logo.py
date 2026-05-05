#!/usr/bin/env python3
"""
FinForge Logo Generator
-----------------------
Generates two 1024x1024 PNG variants (and their source SVGs) of the FinForge
logo: an abstract geometric "F" mark in black + electric cyan.

Outputs (written next to this script):
    finforge.svg            - detailed variant (vector)
    finforge.png            - detailed variant (1024x1024 PNG)
    finforge_minimal.svg    - minimal variant (vector)
    finforge_minimal.png    - minimal variant (1024x1024 PNG)

Requires:
    pip install cairosvg

Usage:
    python3 generate_finforge_logo.py
    python3 generate_finforge_logo.py --size 2048        # different PNG size
    python3 generate_finforge_logo.py --out ./assets     # different output dir
    python3 generate_finforge_logo.py --only minimal     # skip the detailed one
"""

import argparse
import sys
from pathlib import Path


# ------------------------------------------------------------------
# SVG templates. viewBox is 1024x1024 so the math below reads cleanly;
# the PNG output size is independent (the rasterizer scales the vector).
# ------------------------------------------------------------------

DETAILED_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <linearGradient id="cyan" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00E5FF"/>
      <stop offset="50%" stop-color="#00BFFF"/>
      <stop offset="100%" stop-color="#0091EA"/>
    </linearGradient>
    <radialGradient id="bg" cx="50%" cy="40%" r="75%">
      <stop offset="0%" stop-color="#0A0E14"/>
      <stop offset="100%" stop-color="#000000"/>
    </radialGradient>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="haloGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="20"/>
    </filter>
  </defs>

  <!-- Background: rounded square with slight radial depth -->
  <rect width="1024" height="1024" fill="url(#bg)" rx="180"/>

  <!-- Soft cyan halo behind the mark -->
  <g opacity="0.35">
    <path d="M 280 240 L 700 240 L 700 360 L 420 360 L 420 480 L 620 480
             L 620 600 L 420 600 L 420 780 L 280 780 Z"
          fill="url(#cyan)" filter="url(#haloGlow)"/>
  </g>

  <!-- F body: three dark metallic bars with cyan stroke outlines -->
  <g fill="#1a2230" stroke="url(#cyan)" stroke-width="6" stroke-linejoin="miter">
    <path d="M 280 240 L 700 240 L 700 360 L 280 360 Z"/>   <!-- top bar -->
    <path d="M 280 480 L 620 480 L 620 600 L 280 600 Z"/>   <!-- middle bar -->
    <path d="M 280 240 L 420 240 L 420 780 L 280 780 Z"/>   <!-- spine -->
  </g>

  <!-- Cyan accents (glowing) -->
  <g filter="url(#glow)">
    <!-- diagonal cut on top-right of top bar (spark motif) -->
    <path d="M 700 240 L 700 360 L 620 360 L 700 240 Z" fill="url(#cyan)"/>
    <!-- base accent at foot of spine (anvil grounding) -->
    <rect x="280" y="760" width="140" height="20" fill="url(#cyan)"/>
  </g>
  <g filter="url(#glow)" opacity="0.9">
    <!-- diagonal spark crossing the middle bar -->
    <path d="M 600 500 L 680 420 L 695 435 L 615 515 Z" fill="url(#cyan)"/>
  </g>

  <!-- Subtle corner framing ticks -->
  <g stroke="url(#cyan)" stroke-width="4" fill="none" opacity="0.6">
    <path d="M 160 160 L 200 160 M 160 160 L 160 200"/>
    <path d="M 864 160 L 824 160 M 864 160 L 864 200"/>
    <path d="M 160 864 L 200 864 M 160 864 L 160 824"/>
    <path d="M 864 864 L 824 864 M 864 864 L 864 824"/>
  </g>
</svg>
"""

MINIMAL_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <linearGradient id="cyan2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00E5FF"/>
      <stop offset="100%" stop-color="#0091EA"/>
    </linearGradient>
    <filter id="glow2" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <rect width="1024" height="1024" fill="#000000" rx="180"/>

  <!-- Flat cyan F -->
  <g fill="url(#cyan2)">
    <rect x="320" y="260" width="130" height="520"/>        <!-- spine -->
    <rect x="320" y="260" width="400" height="130"/>        <!-- top bar -->
    <rect x="320" y="470" width="300" height="110"/>        <!-- middle bar -->
  </g>

  <!-- Diagonal notch on top-right corner (punches the black through) -->
  <g filter="url(#glow2)">
    <path d="M 720 260 L 720 390 L 640 390 Z" fill="#000000"/>
  </g>
  <g filter="url(#glow2)" opacity="0.9">
    <path d="M 700 275 L 720 275 L 720 295 Z" fill="#FFFFFF"/>
  </g>
</svg>
"""


VARIANTS = {
    "detailed": ("finforge", DETAILED_SVG),
    "minimal":  ("finforge_minimal", MINIMAL_SVG),
}


def render(name_stem: str, svg_source: str, out_dir: Path, png_size: int) -> None:
    """Write SVG source to disk and rasterize to a square PNG at `png_size`."""
    import cairosvg  # imported here so the module-level script works even if
                     # the user only wants --help

    svg_path = out_dir / f"{name_stem}.svg"
    png_path = out_dir / f"{name_stem}.png"

    svg_path.write_text(svg_source, encoding="utf-8")

    cairosvg.svg2png(
        bytestring=svg_source.encode("utf-8"),
        write_to=str(png_path),
        output_width=png_size,
        output_height=png_size,
    )

    kb = png_path.stat().st_size / 1024
    print(f"  {svg_path.name}  ->  {png_path.name}  ({png_size}x{png_size}, {kb:.1f} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate FinForge logo PNGs.")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent,
                        help="Output directory (default: script directory).")
    parser.add_argument("--size", type=int, default=1024,
                        help="PNG width/height in pixels (default: 1024).")
    parser.add_argument("--only", choices=list(VARIANTS.keys()) + ["all"], default="all",
                        help="Render only one variant, or 'all' (default).")
    args = parser.parse_args()

    try:
        import cairosvg  # noqa: F401 — probe for a clearer error than a traceback
    except ImportError:
        print("error: cairosvg is not installed. Run: pip install cairosvg",
              file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    targets = VARIANTS.items() if args.only == "all" else [(args.only, VARIANTS[args.only])]

    print(f"Writing to: {args.out}")
    for _, (stem, svg) in targets:
        render(stem, svg, args.out, args.size)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
