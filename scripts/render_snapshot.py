#!/usr/bin/env python3
"""Render a static MiniCity snapshot for reports/QA (no GUI required)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def render(seed: int, days: int, out: Path) -> Path:
    from dss.core.engine import build_minicity
    sim = build_minicity(seed)
    sim.run(days)
    state = sim.to_dict()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        # A lightweight SVG fallback keeps the artifact available in minimal
        # Python installations.
        width, height = 1200, 760
        locs = state["map"]["locations"]
        circles = []
        for i, (cid, c) in enumerate(state["citizens"].items()):
            loc = locs.get(c.get("location_id"), {})
            x = 60 + int(loc.get("x", i % 30) / 30 * 1080)
            y = 100 + int(loc.get("y", i // 30) / 20 * 580)
            circles.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#72d6a2"/>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
               f'<rect width="100%" height="100%" fill="#111b29"/>'
               f'<text x="30" y="45" fill="white" font-size="24">Digital Society Sandbox · day {days} · seed {seed}</text>'
               + "".join(circles) + "</svg>")
        svg_path = out.with_suffix(".svg")
        svg_path.write_text(svg, encoding="utf-8")
        return svg_path

    image = Image.new("RGB", (1200, 760), "#101923")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 70, 1180, 730), outline="#355065", width=2)
    draw.text((30, 25), f"Digital Society Sandbox · MiniCity · day {days} · seed {seed}", fill="#e7f3f8")
    locs = state["map"]["locations"]

    def xy(loc_id: str | None, i: int = 0):
        loc = locs.get(loc_id or "", {})
        # Spread entities around their zone so a static report image exposes
        # population/business density instead of hiding a whole district in a
        # single pixel.
        jitter_x = ((i * 37) % 17 - 8) * 2.8
        jitter_y = ((i * 19) % 13 - 6) * 3.2
        x = 40 + (float(loc.get("x", i % 30)) / 30.0) * 1120 + jitter_x
        y = 90 + (float(loc.get("y", i // 30)) / 20.0) * 610 + jitter_y
        return int(x), int(y)

    colors = {"Residential": "#355d88", "Commercial": "#c78a43", "Industry": "#a66c55",
              "School": "#7d9b68", "Hospital": "#bf7180", "Government": "#8b7bb0",
              "Park": "#4a8b70", "Transport": "#777d89", "Market": "#c6a84d"}
    for loc in locs.values():
        x, y = xy(loc["id"])
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=colors.get(loc.get("kind"), "#526273"), outline="#d6e5ec")
        draw.text((x + 12, y - 7), loc.get("kind", ""), fill="#9db1bf")
    for i, b in enumerate(state["businesses"].values()):
        x, y = xy(b.get("location_id"), i)
        draw.rectangle((x - 6, y - 6, x + 6, y + 6), fill="#e5a14e")
    for i, c in enumerate(state["citizens"].values()):
        x, y = xy(c.get("location_id"), i)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#75d7a4" if c.get("job_id") else "#e07d88")
    m = state.get("metrics", {})
    draw.text((920, 25), f"Citizens {m.get('population', 0)}  Businesses {m.get('business_count', 0)}  Employment {float(m.get('employment_rate', 0))*100:.1f}%", fill="#b5c8d2")
    draw.text((30, 735), "green=employed citizen · red=unemployed · square=business · ring=zone", fill="#b5c8d2")
    image.save(out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", type=Path, default=Path("artifacts/minicity_snapshot.png"))
    args = ap.parse_args(argv)
    path = render(args.seed, args.days, args.out)
    print(json.dumps({"status": "ok", "path": str(path), "seed": args.seed, "days": args.days}))


if __name__ == "__main__":
    main()
