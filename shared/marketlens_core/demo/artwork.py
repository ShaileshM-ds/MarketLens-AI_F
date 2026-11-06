"""Fictional product artwork for the synthetic Demo catalogue: deterministic, self-contained SVG (no external
images, fonts or links), varied by category, colour and background. Labelled as demo artwork; no real brands.

Run `python -m marketlens_core.demo.artwork <out_dir>` to write one SVG per Demo product plus `fallback.svg`.
The product list is derived from the generator's own constants, so it always matches the Demo database.
"""

import sys
from pathlib import Path

from .generator import BRANDS, CATALOG, COLOURS

N_PRODUCTS = 40
FALLBACK = "fallback.svg"
COLOUR_HEX = {"Graphite": "#3d4350", "Sky Blue": "#4f9fe0", "Olive": "#6f7d3c", "Ivory": "#efe6d2", "Crimson": "#c4283f"}
BACKGROUNDS = [("#e9e4ff", "#c9dcff"), ("#ffe8d6", "#ffd1dc"), ("#dff6ec", "#c9e9ff"), ("#fff4c9", "#ffd9b8"),
               ("#e5f0ff", "#e8dcff"), ("#ffe0e6", "#ffeccf"), ("#e3f7f1", "#efe3ff"), ("#f0f0f5", "#d8e6ff")]


def demo_products() -> list[dict]:
    out = []
    for i in range(N_PRODUCTS):
        slug, sub, noun, _base, _kind = CATALOG[i // 5]
        out.append({"product_id": f"DEMO-P-{i + 1:03d}", "index": i, "category": slug, "noun": noun,
                    "brand": BRANDS[(i * 7) % len(BRANDS)], "colour": COLOURS[i % len(COLOURS)]})
    return out


def _shade(hex_: str, f: float) -> str:
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    m = (lambda c: max(0, min(255, int(c * f)))) if f < 1 else (lambda c: max(0, min(255, int(c + (255 - c) * (f - 1)))))
    return f"#{m(r):02x}{m(g):02x}{m(b):02x}"


def _object(category: str, c: str) -> str:
    d, l2 = _shade(c, 0.62), _shade(c, 1.35)
    s = f'stroke="{d}" stroke-width="4" stroke-linejoin="round"'
    if category == "mens-clothing":
        return (f'<path d="M170 120 L120 145 L85 210 L130 232 L150 200 L150 390 L330 390 L330 200 L350 232 L395 210 L360 145 L310 120 '
                f'Q240 165 170 120 Z" fill="{c}" {s}/><path d="M205 128 Q240 160 275 128" fill="none" stroke="{d}" stroke-width="5"/>'
                f'<path d="M160 215 L160 380" stroke="{l2}" stroke-width="10" opacity=".35"/>')
    if category == "womens-clothing":
        dots = "".join(f'<circle cx="{240 + dx}" cy="{170 + dy}" r="4" fill="{l2}"/>' for dx, dy in ((-18, 10), (18, 10), (0, 30), (-18, 50), (18, 50), (0, 70)))
        return (f'<path d="M195 100 L150 120 L120 185 L155 200 L170 175 L160 410 L320 410 L310 175 L325 200 L360 185 L330 120 L285 100 '
                f'Q240 130 195 100 Z" fill="{c}" {s}/><path d="M240 112 L240 165" stroke="{d}" stroke-width="4"/>{dots}'
                f'<path d="M165 390 L315 390" stroke="{l2}" stroke-width="8" stroke-dasharray="10 8"/>')
    if category == "mobile-phones":
        return (f'<rect x="160" y="90" width="160" height="310" rx="26" fill="{c}" {s}/>'
                f'<rect x="174" y="112" width="132" height="266" rx="16" fill="url(#screen)"/>'
                f'<rect x="220" y="100" width="40" height="6" rx="3" fill="{d}"/><circle cx="240" cy="300" r="26" fill="#ffffff" opacity=".35"/>'
                f'<rect x="196" y="150" width="88" height="10" rx="5" fill="#ffffff" opacity=".7"/><rect x="196" y="172" width="60" height="8" rx="4" fill="#ffffff" opacity=".5"/>')
    if category == "wearables":
        return (f'<rect x="200" y="70" width="80" height="120" rx="18" fill="{d}"/><rect x="200" y="300" width="80" height="120" rx="18" fill="{d}"/>'
                f'<rect x="170" y="160" width="140" height="170" rx="40" fill="{c}" {s}/>'
                f'<rect x="186" y="178" width="108" height="134" rx="30" fill="#14182a"/>'
                f'<circle cx="240" cy="245" r="40" fill="none" stroke="{l2}" stroke-width="8" stroke-dasharray="180 260"/>'
                f'<text x="240" y="252" text-anchor="middle" font-family="sans-serif" font-size="22" font-weight="700" fill="#ffffff">10:08</text>'
                f'<rect x="310" y="215" width="10" height="34" rx="4" fill="{d}"/>')
    if category == "home-appliances":
        return (f'<rect x="140" y="110" width="200" height="270" rx="46" fill="{c}" {s}/>'
                f'<rect x="165" y="230" width="150" height="120" rx="20" fill="{d}"/><rect x="200" y="280" width="80" height="18" rx="9" fill="{l2}"/>'
                f'<circle cx="240" cy="170" r="28" fill="{l2}" {s}/><path d="M240 150 L240 170" stroke="{d}" stroke-width="5" stroke-linecap="round"/>'
                f'<rect x="170" y="380" width="30" height="14" rx="5" fill="{d}"/><rect x="280" y="380" width="30" height="14" rx="5" fill="{d}"/>')
    if category == "computer-accessories":
        keys = "".join(f'<rect x="{110 + col * 30}" y="{200 + row * 30}" width="24" height="24" rx="5" fill="{l2}"/>'
                       for row in range(3) for col in range(9))
        return (f'<rect x="90" y="180" width="300" height="140" rx="22" fill="{c}" {s}/>{keys}'
                f'<rect x="170" y="290" width="140" height="20" rx="6" fill="{l2}"/>')
    if category == "cameras":
        return (f'<rect x="120" y="150" width="240" height="190" rx="34" fill="{c}" {s}/>'
                f'<circle cx="270" cy="245" r="70" fill="{d}"/><circle cx="270" cy="245" r="50" fill="#14182a"/>'
                f'<circle cx="270" cy="245" r="28" fill="url(#lens)"/><circle cx="255" cy="230" r="9" fill="#ffffff" opacity=".7"/>'
                f'<rect x="145" y="175" width="60" height="34" rx="8" fill="{l2}"/><rect x="300" y="130" width="40" height="22" rx="8" fill="{d}"/>')
    # smart-home
    return (f'<rect x="150" y="130" width="180" height="220" rx="48" fill="{c}" {s}/>'
            f'<circle cx="240" cy="230" r="58" fill="{l2}" {s}/><rect x="212" y="205" width="12" height="40" rx="5" fill="{d}"/>'
            f'<rect x="256" y="205" width="12" height="40" rx="5" fill="{d}"/><circle cx="240" cy="315" r="8" fill="#3ddc84"/>')


def product_svg(p: dict) -> str:
    bg1, bg2 = BACKGROUNDS[(p["index"] * 3) % len(BACKGROUNDS)]
    c = COLOUR_HEX[p["colour"]]
    label = f'{p["brand"]} · demo artwork'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 480" width="480" height="480" role="img" '
        f'aria-label="{p["brand"]} {p["noun"]}, {p["colour"]} (synthetic demo artwork)">'
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/></linearGradient>'
        '<linearGradient id="screen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6a5cff"/><stop offset="1" stop-color="#36c2d9"/></linearGradient>'
        '<radialGradient id="lens"><stop offset="0" stop-color="#7aa8ff"/><stop offset="1" stop-color="#1b2140"/></radialGradient></defs>'
        '<rect width="480" height="480" rx="36" fill="url(#bg)"/>'
        f'<circle cx="{80 + (p["index"] * 37) % 320}" cy="{70 + (p["index"] * 53) % 120}" r="70" fill="#ffffff" opacity=".35"/>'
        '<ellipse cx="240" cy="418" rx="150" ry="16" fill="#1b2140" opacity=".12"/>'
        f'{_object(p["category"], c)}'
        f'<rect x="20" y="436" width="{len(label) * 8 + 24}" height="28" rx="14" fill="#ffffff" opacity=".85"/>'
        f'<text x="32" y="455" font-family="sans-serif" font-size="14" font-weight="600" fill="#2a2f45">{label}</text>'
        '</svg>'
    )


def fallback_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 480" width="480" height="480" role="img" aria-label="No product image">'
            '<rect width="480" height="480" rx="36" fill="#eceaf7"/><rect x="150" y="150" width="180" height="180" rx="28" fill="none" stroke="#8a86b8" stroke-width="10"/>'
            '<path d="M150 210 L240 260 L330 210 M240 260 L240 330" fill="none" stroke="#8a86b8" stroke-width="10" stroke-linejoin="round"/>'
            '<text x="240" y="390" text-anchor="middle" font-family="sans-serif" font-size="20" fill="#5d5a85">No product image</text></svg>')


def write_images(out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for p in demo_products():
        name = f'{p["product_id"]}.svg'
        (out_dir / name).write_text(product_svg(p), encoding="utf-8", newline="\n")
        names.append(name)
    (out_dir / FALLBACK).write_text(fallback_svg(), encoding="utf-8", newline="\n")
    return names + [FALLBACK]


if __name__ == "__main__":
    print(len(write_images(Path(sys.argv[1]))), "files")
