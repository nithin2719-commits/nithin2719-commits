#!/usr/bin/env python3
"""Generate the profile README's SVG assets.

GitHub strips CSS and web fonts from READMEs, so every piece of Orbitron /
JetBrains Mono type lives inside an SVG with the font subset + embedded as
base64 WOFF2. Edit the content below and re-run:

    pip install fonttools brotli
    python3 assets/src/build.py
"""
import base64
import datetime as dt
import io
import json
import os
import re
import pathlib
import sys
import urllib.request
from functools import lru_cache

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
CACHE = HERE / ".fonts"

FONT_SOURCES = {
    "Orbitron": "https://github.com/google/fonts/raw/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf",
    "JetBrainsMono": "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}
# css family -> (source, weight)
FACES = {
    "ob": ("Orbitron", 900),
    "om": ("Orbitron", 600),
    "mr": ("JetBrainsMono", 400),
    "mb": ("JetBrainsMono", 700),
}

# ── palette: pure black and white, with three functional greys ──────────────
VOID = "#000000"
SIGNAL = "#FFFFFF"
ASH = "#A3A3A3"     # secondary text
SMOKE = "#5E5E5E"   # tertiary text, idle states
EDGE = "#2E2E2E"    # borders, rules
GRID = "#1F1F1F"    # background marks


# ── fonts ────────────────────────────────────────────────────────────────────
def _source(name):
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{name}.ttf"
    if not path.exists():
        urllib.request.urlretrieve(FONT_SOURCES[name], path)
    return path


@lru_cache(None)
def face(key):
    name, weight = FACES[key]
    f = instancer.instantiateVariableFont(TTFont(_source(name), recalcTimestamp=False), {"wght": weight})
    f.recalcTimestamp = False  # byte-identical rebuilds, so the refresh job only commits real changes
    return f


def measure(key, text, size, ls=0.0):
    f = face(key)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    adv = sum(hmtx[cmap.get(ord(c), cmap[ord("?")])][0] for c in text)
    return adv * size / upm + ls * len(text)


def embed(key, chars):
    f = face(key)
    missing = sorted(c for c in chars if ord(c) not in f.getBestCmap() and c != " ")
    if missing:
        print(f"  ! {key} has no glyph for {missing!r}")
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    sub = TTFont(buf, recalcTimestamp=False)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.hinting = False
    opts.desubroutinize = True
    opts.layout_features = ["kern"]  # no ligatures: fastfetch art and shell text stay literal
    s = subset.Subsetter(opts)
    s.populate(text="".join(sorted(chars)) + " ")
    s.subset(sub)
    out = io.BytesIO()
    sub.flavor = "woff2"
    sub.save(out)
    return base64.b64encode(out.getvalue()).decode()


# ── svg document ─────────────────────────────────────────────────────────────
def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Doc:
    def __init__(self, w, h, title):
        self.w, self.h, self.title = w, h, title
        self.parts, self.css, self.defs = [], [], []
        self.chars = {k: set() for k in FACES}

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, font, size, fill=SIGNAL, anchor="start", ls=0, cls="", extra=""):
        self.chars[font].update(s)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        l = f' letter-spacing="{ls}"' if ls else ""
        c = f' class="{cls}"' if cls else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" '
                 f'fill="{fill}"{a}{l}{c}{extra}>{esc(s)}</text>')

    def render(self):
        faces = "".join(
            f"@font-face{{font-family:{k};src:url(data:font/woff2;base64,{embed(k, v)}) format('woff2')}}"
            for k, v in self.chars.items() if v)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.title)}">'
                f"<title>{esc(self.title)}</title>"
                f"<style>{faces}text{{white-space:pre}}{''.join(self.css)}</style>"
                f"<defs>{''.join(self.defs)}</defs>{''.join(self.parts)}</svg>")

    def save(self, name):
        (OUT / name).write_text(self.render())
        print(f"  {name:<28} {(OUT / name).stat().st_size / 1024:6.1f} KB")


def chamfer(x, y, w, h, tr=0, bl=0, br=0):
    """Rectangle path with 45° cut corners (top-right, bottom-left, bottom-right)."""
    return (f"M{x},{y} H{x + w - tr} L{x + w},{y + tr} V{y + h - br} L{x + w - br},{y + h} "
            f"H{x + bl} L{x},{y + h - bl} Z")


def bracket(x, y, size, dx, dy, stroke=SIGNAL, width=2):
    """L-shaped HUD corner. dx/dy = ±1 picks which way the arms point."""
    return (f'<path d="M{x},{y + dy * size} V{y} H{x + dx * size}" fill="none" '
            f'stroke="{stroke}" stroke-width="{width}"/>')


# ── icons: simple-icons (CC0) where a brand has one, hand-drawn otherwise ────
CUSTOM_ICONS = {
    # radar sweep for nmap
    "nmap": '<g fill="none" stroke="#fff" stroke-width="1.8"><circle cx="12" cy="12" r="10"/>'
            '<circle cx="12" cy="12" r="5.5"/><path d="M12 12 19.2 4.8" stroke-width="2.2"/></g>'
            '<circle cx="12" cy="12" r="1.9"/><circle cx="16.6" cy="15.4" r="1.5"/>',
    # linkedin "in" (removed from simple-icons at linkedin's request)
    "linkedin": '<rect x="1" y="1" width="22" height="22" rx="3"/><g fill="#000"><circle cx="7" cy="6.6" r="1.8"/>'
                '<path d="M5.4 9.5h3.2V19H5.4zM10.6 9.5h3.1v1.4c.6-1 1.8-1.7 3.3-1.7 2.6 0 3.7 1.6 3.7 4.4V19h-3.2'
                'v-4.8c0-1.4-.4-2.3-1.6-2.3-1.3 0-2.1.9-2.1 2.4V19h-3.2z"/></g>',
    # disassembly under a lens for ghidra
    "ghidra": '<path d="M1 3h12v2.2H1zM1 8.2h8v2.2H1zM1 13.4h5v2.2H1z"/>'
              '<g fill="none" stroke="#fff"><circle cx="15.5" cy="14" r="5" stroke-width="2.2"/>'
              '<path d="m19.2 17.8 3.8 4" stroke-width="2.8"/></g>',
}


@lru_cache(None)
def icon_path(slug):
    path = CACHE / "icons" / f"{slug}.svg"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f"https://cdn.jsdelivr.net/npm/simple-icons@15/icons/{slug}.svg", path)
    return re.search(r' d="([^"]+)"', path.read_text()).group(1)


# Arch "A" outline on a 100-unit box (apex at 50,0; feet on y=100), traced as one contour:
# left edge with its shoulder notch, left foot, inner arch, right foot, right notch, right edge.
ARCH_A = [(50, 0), (37.9, 28.5), (50.7, 39.6), (36.5, 31.5), (0, 99.5), (38.4, 82.6), (37.6, 75.9),
          (39.0, 67.2), (43.0, 60.5), (50.7, 57.2), (58.0, 61.0), (61.8, 69.2), (62.5, 77.3), (61.9, 82.7),
          (100, 99.5), (91.6, 83.9), (74.3, 72.1), (88.1, 77.5)]
# the part the signal rides: up the left edge, over the apex, down the right edge
ARCH_RIDGE = [(0, 99.5), (36.5, 31.5), (50.7, 39.6), (37.9, 28.5), (50, 0), (88.1, 77.5), (74.3, 72.1),
              (91.6, 83.9), (100, 99.5)]


def arch_pts(points, cx, base, size):
    return [(cx + (x - 50) / 100 * size, base - size + y / 100 * size) for x, y in points]


def fmt_pts(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def katana(cx, apex, size, tilt=0):
    """Katana through the A, drawn hilt-up: kashira, ito-wrapped tsuka over white samegawa,
    fuchi, tsuba, habaki, then a gently curved blade with its shinogi ridge and a wavy hamon."""
    u = size / 100
    P = lambda x, y: f"{cx + x * u:.2f},{apex + y * u:.2f}"
    top, fuchi, tsuba, blade0, tip = -66, -14, -10, -2, 118
    out = []
    # tsuka: white samegawa showing through dark crossed wrap = the classic row of diamonds
    out.append(f'<path d="M{P(-3.7, top + 3)} L{P(3.7, top + 3)} L{P(3.3, fuchi)} L{P(-3.3, fuchi)} Z" fill="#e9e9e9"/>')
    out.append(f'<path d="M{P(-3.7, top + 3)} L{P(3.7, top + 3)} L{P(3.3, fuchi)} L{P(-3.3, fuchi)} Z" fill="#0b0b0b" '
               f'mask="url(#samegawa)"/>')
    out.append(f'<rect x="{cx - 4 * u:.2f}" y="{apex + top * u:.2f}" width="{8 * u:.2f}" height="{3.4 * u:.2f}" '
               f'rx="{1.2 * u:.2f}" fill="#bdbdbd"/>')                                          # kashira
    out.append(f'<rect x="{cx - 3.6 * u:.2f}" y="{apex + fuchi * u:.2f}" width="{7.2 * u:.2f}" height="{2.6 * u:.2f}" '
               f'fill="#bdbdbd"/>')                                                             # fuchi
    out.append(f'<ellipse cx="{cx}" cy="{apex + tsuba * u:.2f}" rx="{10 * u:.2f}" ry="{2.5 * u:.2f}" '
               f'fill="#1c1c1c" stroke="#e6e6e6" stroke-width="{0.7 * u:.2f}"/>')                  # tsuba
    out.append(f'<rect x="{cx - 2.9 * u:.2f}" y="{apex + (tsuba + 2.3) * u:.2f}" width="{5.8 * u:.2f}" '
               f'height="{6 * u:.2f}" fill="#d6d6d6"/>')                                         # habaki
    # blade: back (mune) on the left, edge (ha) on the right, curving gently toward the edge
    off = lambda y: 0.0  # dead straight: it has to run true through the apex
    ys = [blade0 + i * (104 - blade0) / 24 for i in range(25)]
    mune = [(-2.55 + off(y), y) for y in ys]
    ha = [(2.55 + off(y), y) for y in reversed(ys)]
    point = [(-2.55, 104), (0, tip), (2.55, 104)]
    blade = [mune[0]] + mune[1:] + point + ha
    out.append(f'<path d="M{" L".join(P(x, y) for x, y in blade)} Z" fill="url(#steel)"/>')
    out.append(f'<path d="M{" L".join(P(0, y) for y in ys)}" fill="none" stroke="#7a7a7a" '
               f'stroke-width="{0.35 * u:.2f}"/>')                                              # shinogi
    import math
    hy = [blade0 + 4 + i * 1.6 for i in range(int((100 - blade0 - 4) / 1.6))]
    out.append(f'<path d="M{" L".join(P(1.35 + 0.5 * math.sin(y / 2.6), y) for y in hy)}" fill="none" '
               f'stroke="#ffffff" stroke-width="{0.5 * u:.2f}" opacity=".85"/>')                 # hamon
    out.append(f'<path d="M{P(-2.55, 104)} L{P(2.55, 104)}" stroke="#9a9a9a" '
               f'stroke-width="{0.35 * u:.2f}"/>')                                              # yokote
    return f'<g transform="rotate({tilt} {cx} {apex})">{"".join(out)}</g>'


def katana_defs(cx, apex, size):
    u = size / 100
    top, fuchi = -66, -14
    diamonds = "".join(
        f'<path d="M{cx:.2f},{apex + (y - 2.4) * u:.2f} L{cx + 2.6 * u:.2f},{apex + y * u:.2f} '
        f'L{cx:.2f},{apex + (y + 2.4) * u:.2f} L{cx - 2.6 * u:.2f},{apex + y * u:.2f} Z" fill="#000"/>'
        for y in [top + 6.5 + i * 5.6 for i in range(9)])
    return (f'<mask id="samegawa" maskUnits="userSpaceOnUse"><rect x="0" y="0" width="5000" height="5000" fill="#fff"/>'
            f'{diamonds}</mask>'
            '<linearGradient id="steel" x1="0" y1="0" x2="1" y2="0">'
            '<stop offset="0" stop-color="#6b6b6b"/><stop offset=".45" stop-color="#b4b4b4"/>'
            '<stop offset=".62" stop-color="#e9e9e9"/><stop offset="1" stop-color="#ffffff"/></linearGradient>')


BLADE_GRADIENT = ('<linearGradient id="blade" x1="0" y1="0" x2="1" y2="0">'
                  '<stop offset="0" stop-color="#5e5e5e"/><stop offset=".55" stop-color="#bdbdbd"/>'
                  '<stop offset="1" stop-color="#ffffff"/></linearGradient>')


def blackarch_icon():
    """BlackArch's mark at icon size: the A in outline, a sword straight through it."""
    a = fmt_pts(arch_pts(ARCH_A, 12, 23.4, 17.5))
    return (f'<polygon points="{a}" fill="none" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/>'
            '<rect x="11.3" y="5.2" width="1.4" height="18.8"/><rect x="8.9" y="4" width="6.2" height="1.4"/>'
            '<rect x="10.9" y="0.2" width="2.2" height="3.8"/>')


def icon(slug, x, y, size, fill=SIGNAL):
    inner = blackarch_icon() if slug == "blackarch" else CUSTOM_ICONS.get(slug) or f'<path d="{icon_path(slug)}"/>'
    return f'<g transform="translate({x:.1f},{y:.1f}) scale({size / 24:.4f})" fill="{fill}">{inner}</g>'


def tear(d, text_svg, slices, period, delay, cls):
    """Horizontal glitch: slices of `text_svg` jump sideways for a few frames each period."""
    for n, (y0, h, fill, dx) in enumerate(slices):
        cid = f"{cls}{n}"
        d.defs.append(f'<clipPath id="{cid}"><rect x="0" y="{y0:.1f}" width="{d.w}" height="{h}"/></clipPath>')
        d.add(f'<g clip-path="url(#{cid})"><g class="gl {cid}">'
              f'<rect x="0" y="{y0:.1f}" width="{d.w}" height="{h}" fill="{VOID}"/>'
              f'{text_svg.replace("FILL", fill)}</g></g>')
        a, b = 90 + n * 0.6, 91.5 + n * 0.6
        d.css.append(f".{cid}{{opacity:0;animation:{cid} {period}s linear {delay + n * 0.04:.2f}s infinite}}"
                     f"@keyframes {cid}{{0%,{a}%,100%{{opacity:0;transform:none}}"
                     f"{a + 0.3:.1f}%{{opacity:1;transform:translateX({dx}px)}}"
                     f"{b:.1f}%{{opacity:1;transform:translateX({-dx * 0.6:.0f}px)}}{b + 0.8:.1f}%{{opacity:0}}}}")


def glow(d, fid="glow", std=3.0, layers=2):
    """Neon bloom: the element plus blurred copies of itself."""
    if any(f'id="{fid}"' in x for x in d.defs):
        return
    d.defs.append(f'<filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%">'
                  f'<feGaussianBlur stdDeviation="{std}" result="b"/><feMerge>'
                  + '<feMergeNode in="b"/>' * layers + '<feMergeNode in="SourceGraphic"/></feMerge></filter>')


def pulse(d, path, length, cls, period, delay=0.0, travel=1.0, dash=70, width=2.2):
    """A bright glowing segment that runs along `path`, then rests for the rest of `period`."""
    glow(d)
    d.add(f'<path class="pulse {cls}" d="{path}" fill="none" stroke="#fff" stroke-width="{width}" '
          f'stroke-linecap="round" stroke-dasharray="{dash} {length + dash:.0f}" stroke-dashoffset="{dash}" '
          f'filter="url(#glow)"/>')
    d.css.append(f".{cls}{{animation:{cls} {period}s linear {delay:.2f}s infinite}}"
                 f"@keyframes {cls}{{0%{{stroke-dashoffset:{dash}}}{travel * 100:.1f}%,100%{{stroke-dashoffset:-{length:.0f}}}}}")


REDUCED = "@media (prefers-reduced-motion:reduce){*{animation:none!important}.g,.gl,.pre,.scan{display:none}.f,.late,.t,.ln,.hc{opacity:1!important}.fl,.kx,.pulse,.beam,.sel{display:none}.mq{transform:none!important}}"


# ── hero ─────────────────────────────────────────────────────────────────────
def hero():
    W, H = 1200, 440
    d = Doc(W, H, "NITHIN — cybersecurity, ethical hacking, AI/ML")
    d.add(f'<rect width="{W}" height="{H}" fill="{VOID}"/>')

    # crosshair field, fading out toward the edges
    d.defs.append(
        '<radialGradient id="fade" cx="50%" cy="50%" r="60%">'
        '<stop offset="0" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="m"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>'
        '<pattern id="x" width="60" height="60" patternUnits="userSpaceOnUse" x="0" y="10">'
        f'<path d="M30,26 V34 M26,30 H34" stroke="{SMOKE}" stroke-width="1"/></pattern>')
    d.add(f'<rect width="{W}" height="{H}" fill="url(#x)" mask="url(#m)" opacity=".55"/>')

    # frame
    d.add(f'<path d="{chamfer(14, 14, W - 28, H - 28, tr=30, bl=30)}" fill="none" stroke="{EDGE}"/>')
    d.add(bracket(14, 14, 26, 1, 1))
    d.add(bracket(W - 14, H - 14, 26, -1, -1))
    fw, fh, cut = W - 28, H - 28, 30
    perim = 2 * (fw - cut) + 2 * (fh - cut) + 2 * cut * 2 ** 0.5
    pulse(d, chamfer(14, 14, fw, fh, tr=cut, bl=cut), perim, "frame", 9, 2.4, dash=170, width=2)
    d.defs.append('<filter id="neon" x="-20%" y="-40%" width="140%" height="180%">'
                  '<feGaussianBlur stdDeviation="9" result="b"/>'
                  '<feComponentTransfer in="b" result="s"><feFuncA type="linear" slope=".6"/></feComponentTransfer>'
                  '<feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')

    # prompt line + status that flips once the name resolves
    prompt = "root@blackarch:~# ./decrypt --target nithin"
    d.add(icon("blackarch", 48, 43, 25))
    d.text(82, 62, prompt, "mr", 15, ASH)
    cx = 82 + measure("mr", prompt, 15) + 8
    d.add(f'<rect class="cur" x="{cx:.1f}" y="49" width="9" height="17" fill="{SIGNAL}"/>')
    d.text(W - 52, 62, "DECRYPTING …", "mr", 13, SMOKE, "end", 2, "pre")
    d.text(W - 52, 62, "ACCESS GRANTED", "mb", 13, SIGNAL, "end", 2, "f late", ' style="animation-delay:1.55s"')
    crit = "CRITICAL"
    cx_ = W - 52 - measure("mb", crit, 11, 2) + 2
    d.text(W - 52, 86, crit, "mb", 11, SIGNAL, "end", 2, "f late alarm", ' style="animation-delay:2.05s"')
    for i in range(5):
        bx = cx_ - 14 - (5 - i) * 9
        d.add(f'<rect class="f late" style="animation-delay:{1.7 + i * 0.07:.2f}s" x="{bx:.1f}" y="76" '
              f'width="6" height="11" fill="{SIGNAL}"/>')
    d.text(cx_ - 14 - 5 * 9 - 10, 86, "THREAT LEVEL", "mr", 11, SMOKE, "end", 2, "f late", ' style="animation-delay:1.65s"')

    # the name: each letter scrambles through noise, then locks in place
    name, size, ls = "NITHIN", 132, 10
    noise = "#%&@$X0K7/<>?*=+"
    total = measure("ob", name, size, ls) - ls
    x, base = (W - total) / 2, 262
    cells = []
    for i, ch in enumerate(name):
        adv = measure("ob", ch, size)
        cells.append((x + adv / 2, ch))
        x += adv + ls

    step, start = 0.06, 0.35
    for i, (cx, ch) in enumerate(cells):
        t0 = start + i * 0.13
        for k in range(7):
            g = noise[(i * 5 + k * 3) % len(noise)]
            d.text(cx, base, g, "ob", size, ASH if k % 2 else SIGNAL, "middle", cls="g",
                   extra=f' style="animation-delay:{t0 + k * step:.2f}s"')
        d.text(cx, base, ch, "ob", size, SIGNAL, "middle", cls="f",
               extra=f' style="animation-delay:{t0 + 7 * step:.2f}s"')

    # glitch tears: two horizontal slices of the word, shoved sideways for a few frames
    top = base - size * 0.72
    for n, (y0, hgt, fill) in enumerate([(top + 18, 22, SIGNAL), (top + 58, 14, ASH)]):
        d.defs.append(f'<clipPath id="s{n}"><rect x="0" y="{y0:.0f}" width="{W}" height="{hgt}"/></clipPath>')
        letters = "".join(
            f'<text x="{cx:.1f}" y="{base}" font-family="ob" font-size="{size}" fill="{fill}" '
            f'text-anchor="middle">{ch}</text>' for cx, ch in cells)
        d.add(f'<g clip-path="url(#s{n})"><g class="gl gl{n}">'
              f'<rect x="0" y="{y0:.0f}" width="{W}" height="{hgt}" fill="{VOID}"/>{letters}</g></g>')

    sub = "CYBERSECURITY  //  ETHICAL HACKING  //  AI + ML"
    d.text(W / 2, 318, sub, "om", 17, ASH, "middle", 7, "f late", ' style="animation-delay:1.6s"')

    # tmux-style status bar
    by = 366
    d.add(f'<rect x="40" y="{by}" width="{W - 80}" height="28" fill="#111111"/>')
    tag = " NITHIN "
    tw = measure("mb", tag, 13)
    d.add(f'<rect x="40" y="{by}" width="{tw + 8:.1f}" height="28" fill="{SIGNAL}"/>')
    d.text(44, by + 19, tag, "mb", 13, VOID)
    x = 40 + tw + 26
    for win, active in [("0:recon", False), ("1:exploit*", True), ("2:report", False), ("3:learn", False)]:
        d.text(x, by + 19, win, "mb" if active else "mr", 13, SIGNAL if active else SMOKE)
        x += measure("mr", win, 13) + 22
    right = "B.E CSE  │  INDIA  │  BLACKARCH  │  UTC+05:30 "
    d.text(W - 40 - 92, by + 19, right, "mr", 13, ASH, "end")
    d.add(f'<rect x="{W - 40 - 84}" y="{by}" width="84" height="28" fill="{SIGNAL}"/>')
    d.text(W - 40 - 42, by + 19, "● LIVE", "mb", 13, VOID, "middle")

    d.css.append(
        ".g{opacity:0;animation:blip .06s linear forwards}"
        "@keyframes blip{0%,99%{opacity:1}100%{opacity:0}}"
        ".f{opacity:0;animation:lock .01s linear forwards}"
        "@keyframes lock{to{opacity:1}}"
        ".pre{animation:gone .01s linear 1.55s forwards}"
        "@keyframes gone{to{opacity:0}}"
        ".cur{animation:blink 1.1s steps(1) infinite}"
        "@keyframes blink{50%{opacity:0}}"
        ".alarm{animation:lock .01s linear 2.05s forwards,alarm 1.6s steps(1) 2.6s infinite}"
        "@keyframes alarm{50%{opacity:.3}}"
        ".gl{opacity:0;animation:tear 7s linear 2.6s infinite}"
        ".gl1{animation-name:tear2}"
        "@keyframes tear{0%,93%,100%{opacity:0;transform:translateX(0)}"
        "93.5%{opacity:1;transform:translateX(-14px)}95%{opacity:1;transform:translateX(9px)}96%{opacity:0}}"
        "@keyframes tear2{0%,93.8%,100%{opacity:0;transform:translateX(0)}"
        "94.2%{opacity:1;transform:translateX(18px)}95.6%{opacity:1;transform:translateX(-6px)}96.4%{opacity:0}}"
        + REDUCED)
    d.save("hero.svg")


# ── section headers ──────────────────────────────────────────────────────────
def header(slug, title, note, delay=0.0):
    W, H = 1000, 64
    d = Doc(W, H, title)
    d.add(f'<path d="{chamfer(0, 0, W, H, br=18)}" fill="{VOID}"/>')
    d.add(f'<rect x="0" y="14" width="6" height="36" fill="{SIGNAL}"/>')
    d.text(28, 43, title, "ob", 26, SIGNAL, ls=4)
    t = (f'<text x="28" y="43" font-family="ob" font-size="26" letter-spacing="4" fill="FILL">'
         f'{esc(title)}</text>')
    tear(d, t, [(24, 8, SIGNAL, 9), (35, 6, ASH, -12)], 8, 1.2 + delay, "h")
    d.css.append(REDUCED)
    t_end = 28 + measure("ob", title, 26, 4) + 22
    n_start = W - 36 - measure("mr", note, 13)
    d.text(W - 36, 41, note, "mr", 13, ASH, "end")
    d.add(f'<rect x="{t_end:.1f}" y="34" width="4" height="4" fill="{SIGNAL}"/>')
    d.add(f'<path d="M{t_end + 10:.1f},36 H{n_start - 22:.1f}" stroke="{EDGE}"/>')
    pulse(d, f"M{t_end + 10:.1f},36 H{n_start - 22:.1f}", n_start - 32 - t_end, "rule", 6, 0.6 + delay * 0.7, 0.4)
    d.css.append(REDUCED)
    d.save(f"h-{slug}.svg")


# ── fastfetch card ───────────────────────────────────────────────────────────
# fastfetch's built-in BlackArch logo (fastfetch --logo blackarch)
BLACKARCH = r"""                     00
                     11
                    ====
                    .//
                   `o//:
                  `+o//o:
                 `+oo//oo:
                 -+oo//oo+:
               `/:-:+//ooo+:
              `/+++++//+++++:
             `/++++++//++++++:
            `/+++oooo//ooooooo/`
           ./ooosssso//osssssso+`
          .oossssso-`//`/ossssss+`
         -osssssso.  //  :ssssssso.
        :osssssss/   //   osssso+++.
       /ossssssss/   //   +ssssooo/-
     `/ossssso+/:-   //   -:/+osssso+-
    `+sso+:-`        //       `.-/+oso:
   `++:.             //            `-/+/
   .`                /                `/""".split("\n")
SWORD = {21, 22}  # the blade column, drawn bright; the body sits back in grey


FETCH = [
    ("OS", "BlackArch Linux x86_64"),
    ("WM", "Hyprland  (graphite-mono rice)"),
    ("Shell", "zsh"),
    ("Degree", "B.E CSE, Cybersecurity"),
    ("Location", "India"),
    ("Focus", "Ethical hacking, CTFs, AI/ML, backend"),
    ("Learning", "Django, FastAPI, malware analysis"),
    ("Toolkit", "Burp Suite, Wireshark, Metasploit, Ghidra"),
    ("Building", "KRYPT, AGX, BlackArch Toolbox"),
    ("Motto", "Break things ethically. Fix them permanently."),
]


def fetch():
    W, H = 1000, 512
    d = Doc(W, H, "fastfetch: nithin@blackarch")
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=24, bl=24)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.add(f'<path d="M0.5,40 H{W - 0.5}" stroke="{EDGE}"/>')
    for i in range(3):
        d.add(f'<rect x="{22 + i * 18}" y="16" width="9" height="9" fill="none" stroke="{SMOKE}"/>')
    d.text(W / 2, 25, "nithin@blackarch: ~", "mr", 12, SMOKE, "middle")
    d.text(W - 30, 25, "zsh", "mr", 12, SMOKE, "end")

    d.text(32, 76, "~", "mb", 14, SIGNAL)
    d.text(50, 76, "❯ fastfetch", "mr", 14, ASH)

    lh, y0 = 16.5, 112
    for i, line in enumerate(BLACKARCH):
        runs, cur, bright = [], "", None
        for col, ch in enumerate(line):
            hot = i < 3 or (col in SWORD and ch in "/=01")
            if bright is not None and hot != bright and cur:
                runs.append((cur, bright)); cur = ""
            cur, bright = cur + ch, hot
        runs.append((cur, bright))
        d.chars["mb"].update(line)
        spans = "".join(f'<tspan fill="{SIGNAL if hot else ASH}">{esc(r)}</tspan>' for r, hot in runs)
        d.add(f'<text x="36" y="{y0 + i * lh:.1f}" font-family="mb" font-size="13.5" class="ln" '
              f'style="animation-delay:{0.3 + i * 0.03:.2f}s">{spans}</text>')
    y0 += 14

    x = 420
    d.text(x, y0, "nithin", "mb", 16, SIGNAL)
    d.text(x + measure("mb", "nithin", 16), y0, "@", "mr", 16, SMOKE)
    d.text(x + measure("mb", "nithin@", 16), y0, "blackarch", "mb", 16, SIGNAL)
    d.add(f'<path d="M{x},{y0 + 12} H{x + measure("mb", "nithin@blackarch", 16):.0f}" stroke="{SMOKE}" stroke-dasharray="3 3"/>')
    for i, (k, v) in enumerate(FETCH):
        y = y0 + 40 + i * 26
        late = f' style="animation-delay:{0.95 + i * 0.06:.2f}s"'
        d.text(x, y, k, "mb", 14, SIGNAL, cls="ln", extra=late)
        d.text(x + 104, y, v, "mr", 14, ASH, cls="ln", extra=late)

    # the usual colour blocks, in greyscale
    gy = y0 + 40 + len(FETCH) * 26 - 6
    for i, c in enumerate(["#000", "#1c1c1c", "#383838", "#555", "#717171", "#8e8e8e", "#c6c6c6", "#fff"]):
        d.add(f'<rect x="{x + i * 30}" y="{gy}" width="30" height="16" fill="{c}" stroke="{EDGE}"/>')

    d.text(32, H - 26, "~", "mb", 14, SIGNAL)
    d.text(50, H - 26, "❯", "mr", 14, ASH)
    d.add(f'<rect class="cur" x="68" y="{H - 39}" width="9" height="17" fill="{SIGNAL}"/>')
    d.css.append(".cur{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
                 ".ln{opacity:0;animation:on .01s linear forwards}@keyframes on{to{opacity:1}}"
                 ".sw{opacity:.25;animation:sw 3.2s linear infinite}"
                 "@keyframes sw{0%,100%{opacity:.25}6%{opacity:1}22%{opacity:.25}}" + REDUCED)
    d.save("fetch.svg")


# ── arsenal: a loadout rack instead of badge soup ───────────────────────────
ARSENAL = [
    (("OFFENSIVE", "SECURITY"), [
        ("blackarch", "BlackArch", "pentest distro"), ("burpsuite", "Burp Suite", "web proxy"),
        ("metasploit", "Metasploit", "exploitation"), ("wireshark", "Wireshark", "pcap analysis"),
        ("nmap", "Nmap", "recon + scan"), ("ghidra", "Ghidra", "reverse eng.")]),
    (("LANGUAGES", "+ BACKEND"), [
        ("python", "Python", "main language"), ("c", "C", "systems"), ("gnubash", "Bash", "automation"),
        ("javascript", "JavaScript", "web"), ("django", "Django", "backend"), ("fastapi", "FastAPI", "apis")]),
    (("AI / ML", ""), [
        ("tensorflow", "TensorFlow", "deep learning"), ("scikitlearn", "scikit-learn", "classic ml"),
        ("nvidia", "CUDA", "rtx 3070 ti"), ("ollama", "Ollama", "local llms"),
        ("claude", "Claude Code", "agent ops"), None]),
    (("SYSTEMS", "+ CREATIVE"), [
        ("archlinux", "Arch Linux", "base os"), ("hyprland", "Hyprland", "wayland wm"),
        ("docker", "Docker", "containers"), ("git", "Git", "versioning"),
        ("blender", "Blender", "3d"), ("canva", "Canva", "design")]),
]


def arsenal():
    W, pad, rh, gap, top = 1000, 24, 40, 8, 56
    H = top + len(ARSENAL) * (rh + gap) - gap + 22
    count = sum(1 for _, tools in ARSENAL for t in tools if t)
    d = Doc(W, H, "Arsenal: " + ", ".join(t[1] for _, tools in ARSENAL for t in tools if t))
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=20, bl=20)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.add(f'<path d="M0.5,36 H{W - 0.5}" stroke="{EDGE}"/>')
    pulse(d, f"M0.5,36 H{W - 0.5}", W - 1, "top", 6, 1.6, 0.4, dash=90)
    d.text(pad, 23, "/opt/arsenal", "mr", 11.5, SMOKE)
    d.text(W - pad - 4, 23, "loading modules …", "mr", 11.5, SMOKE, "end", cls="pre")
    msg = f"{count} modules online"
    d.text(W - pad - 4, 23, msg, "mr", 11.5, ASH, "end", cls="f late", extra=' style="animation-delay:1.3s"')
    d.add(f'<rect class="f late" style="animation-delay:1.3s" x="{W - pad - 18 - measure("mr", msg, 11.5):.1f}" '
          f'y="15" width="7" height="7" fill="{SIGNAL}"/>')

    cat_w = 150
    x0 = pad + cat_w
    tw = (W - pad - x0 - 5 * gap) / 6
    k = 0
    for r, ((l1, _), tools) in enumerate(ARSENAL):
        y = top + r * (rh + gap)
        d.add(f'<rect x="{pad}" y="{y}" width="3" height="{rh}" fill="{SIGNAL}"/>')
        d.text(pad + 14, y + 17, l1, "ob", 12, SIGNAL, ls=1.5)
        d.text(pad + 14, y + 32, f"{sum(1 for t in tools if t):02d} modules", "mr", 10, SMOKE)
        for c, tool in enumerate(tools):
            x = x0 + c * (tw + gap)
            shape = chamfer(x + 0.5, y + 0.5, tw - 1, rh - 1, tr=8)
            if tool is None:
                d.add(f'<path d="{shape}" fill="none" stroke="{SMOKE}" stroke-dasharray="3 4"/>')
                d.text(x + tw / 2, y + 24, "+ slot open", "mr", 10, SMOKE, "middle")
                continue
            slug, name, _ = tool
            label = name.upper()
            size = min(10.5, 10.5 * (tw - 46) / measure("om", label, 10.5, 1))
            delay = 0.2 + k * 0.035
            k += 1
            d.chars["om"].update(label)
            inner = (f'<path d="{shape}" fill="{VOID}" stroke="{EDGE}"/>' + icon(slug, x + 11, y + 12, 16)
                     + f'<text x="{x + 35:.1f}" y="{y + 24.5}" font-family="om" font-size="{size:.2f}" '
                       f'letter-spacing="1" fill="{SIGNAL}">{esc(label)}</text>')
            d.add(f'<g class="t" style="animation-delay:{delay:.2f}s">{inner}</g>')
            d.add(f'<path class="fl" style="animation-delay:{delay:.2f}s" d="{shape}" fill="none" '
                  f'stroke="{SIGNAL}" stroke-width="1.5" filter="url(#glow)"/>')

    d.defs.append('<linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">'
                  '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                  '<stop offset=".85" stop-color="#fff" stop-opacity=".06"/>'
                  '<stop offset="1" stop-color="#fff" stop-opacity=".25"/></linearGradient>')
    d.add(f'<rect class="scan" x="1" y="-50" width="{W - 2}" height="50" fill="url(#sg)"/>')
    d.css.append(
        ".t{animation:boot .45s linear both}"
        "@keyframes boot{0%,40%{opacity:.07}42%{opacity:1}55%{opacity:.3}68%,100%{opacity:1}}"
        ".fl{opacity:0;animation:flash .55s ease-out both}@keyframes flash{0%{opacity:0}35%{opacity:1}100%{opacity:0}}"
        ".f{opacity:0;animation:lock .01s linear forwards}@keyframes lock{to{opacity:1}}"
        ".pre{animation:gone .01s linear 1.3s forwards}@keyframes gone{to{opacity:0}}"
        f".scan{{animation:scan 5s linear 1.5s infinite}}"
        f"@keyframes scan{{0%{{transform:translateY(36px)}}40%,100%{{transform:translateY({H + 50}px)}}}}"
        + REDUCED)
    d.save("arsenal.svg")


# ── live-feed ticker under the hero ─────────────────────────────────────────
FEED = ["The quieter you become, the more you are able to hear.",
        "Nah, I'd hack.",
        "Security is a process, not a product. (Bruce Schneier)",
        "Amateurs hack systems, professionals hack people. (Bruce Schneier)",
        "Hack the planet!",
        "If it's connected, it's vulnerable.",
        "Root is not a privilege. It's a responsibility.",
        "I don't hack systems. I understand them.",
        "Break things ethically. Fix them permanently."]


def ticker():
    W, H = 1000, 40
    d = Doc(W, H, "Intercepted: " + " / ".join(FEED))
    d.add(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" fill="{VOID}" stroke="{EDGE}"/>')
    tag = "INTERCEPT"
    cw = measure("om", tag, 11, 2) + 44
    d.add(f'<path d="{chamfer(0, 0, cw, H, br=12)}" fill="{SIGNAL}"/>')
    d.add(f'<rect class="cur" x="14" y="16" width="8" height="8" fill="{VOID}"/>')
    d.text(30, 24.5, tag, "om", 11, VOID, ls=2)

    sep = "   ///   "
    spans, plain = "", ""
    for item in FEED:
        spans += f'<tspan fill="{ASH}">{esc(item)}</tspan><tspan fill="{SMOKE}">{sep}</tspan>'
        plain += item + sep
    d.chars["mr"].update(plain)
    L = measure("mr", plain, 12.5)
    d.defs.append(f'<clipPath id="tk"><rect x="{cw + 4:.0f}" y="0" width="{W - cw - 5:.0f}" height="{H}"/></clipPath>')
    row = "".join(f'<text x="{cw + 18 + i * L:.1f}" y="25" font-family="mr" font-size="12.5">{spans}</text>' for i in range(3))
    d.add(f'<g clip-path="url(#tk)"><g class="mq">{row}</g></g>')
    d.css.append(f".mq{{animation:mq {L / 48:.1f}s linear infinite}}@keyframes mq{{to{{transform:translateX(-{L:.1f}px)}}}}"
                 ".cur{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}" + REDUCED)
    d.save("ticker.svg")


# ── uplink chips ────────────────────────────────────────────
def chip(slug, ico, name, handle):
    H = 52
    nw = max(measure("om", name, 12, 2), measure("mr", handle, 11))
    W = round(16 + 22 + 14 + nw + 24)
    d = Doc(W, H, f"{name}: {handle}")
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, br=12)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.add(icon(ico, 16, 15, 22))
    d.text(52, 24, name, "om", 12, SIGNAL, ls=2)
    d.text(52, 40, handle, "mr", 11, ASH)
    d.save(f"c-{slug}.svg")


# ── operations: one `ls -la` row per project, a scan wave running down the list ──
# KRYPT is private, so the API can't list it — it stays pinned. Everything else is live:
# your most recently pushed original repos, newest first.
OPS_PINNED = [("KRYPT", "Autonomous CTF triage and flag hunter.", "PRIVATE", True)]
OPS_LIVE = 5
OPS_NOTES = {  # hand-written one-liners; other repos use their About text, else their README's first line
    "AGX": "Operations console for autonomous coding agents.",
    "blackarch_toolbox": "One menu for all ~4000 BlackArch tools.",
    "HYPRLAND-CONFIGS": "Graphite-monochrome Hyprland rice for Arch.",
    "Medios": "Offline pharmacy POS and inventory system.",
    "Mailflow": "Gmail threat detection + heuristic defense.",
}


def readme_blurb(repo):
    try:
        text = _get(f"https://raw.githubusercontent.com/{USER}/{repo}/HEAD/README.md", as_json=False)
    except Exception:
        return ""
    fence, para = False, []
    for line in text.splitlines():
        t = line.strip()
        if t.startswith("```"):
            fence = not fence
            continue
        if fence or not t or (t[0] in "#<|![-=*" and not t.startswith("**")):
            if para:  # the first real paragraph has ended
                break
            continue
        t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t.lstrip("> ").strip())
        if not para and re.fullmatch(r"\*\*[^*]{12,}\*\*", t):  # a bold tagline is a complete one-liner
            return t.strip("*").strip()
        t = re.sub(r"[*_`]", "", t).strip()
        if para or len(t) > 12:
            para.append(t)
    text = " ".join(para)
    return re.split(r"(?<=[.!?])\s", text)[0] if text else ""


def ops_data():
    """Rows for the OPERATIONS panel: KRYPT pinned, then the most recently pushed original repos."""
    cache = HERE / "ops.json"
    try:
        repos = _get(f"https://api.github.com/users/{USER}/repos?per_page=100&sort=pushed")
        rows = [{"name": n, "desc": dsc, "chip": c, "private": True, "pushed": None, "pid": 2719}
                for n, dsc, c, _ in OPS_PINNED]
        for r in [r for r in repos if not r["fork"] and r["name"].lower() != USER.lower()][:OPS_LIVE]:
            rows.append({
                "name": r["name"].replace("_", " ").upper(),
                "desc": OPS_NOTES.get(r["name"]) or (r["description"] or "").strip() or readme_blurb(r["name"]) or "—",
                "chip": (r["language"] or "repo").upper(), "private": False,
                "pushed": r["pushed_at"][:10], "pid": 3000 + r["id"] % 60000})
        cache.write_text(json.dumps(rows))
        return rows
    except Exception as e:
        print(f"  ! repo fetch failed ({e}); using {cache.name}")
        return json.loads(cache.read_text())


def ops():
    """OPERATIONS as `htop`: each project is a process; real push dates drive state, bars and age."""
    rows = ops_data()
    today = dt.date.today()
    for r in rows:
        r["age"] = (today - dt.date.fromisoformat(r["pushed"])).days if r["pushed"] else None
    try:  # load average = your real commits/day over 7, 30 and 90 days
        days = json.loads((HERE / "telemetry.json").read_text())["days"]
        load = "  ".join(f"{sum(x['count'] for x in days[-n:]) / n:.1f}" for n in (7, 30, 90))
    except Exception:
        load = "—"
    running = sum(1 for r in rows if r["private"] or (r["age"] is not None and r["age"] <= 7))

    W, pad, top, hh, rh = 1000, 24, 40, 24, 36
    body = top + hh
    H = body + len(rows) * rh + 8 + 30
    d = Doc(W, H, "Operations: " + "; ".join(f"{r['name']} — {r['desc']}" for r in rows))
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=20, bl=20)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.text(pad, 25, "~ ❯ htop -u nithin", "mr", 11.5, SMOKE)
    d.text(W - pad, 25, f"tasks: {len(rows)}, {running} running   load average: {load}", "mr", 11.5, ASH, "end")

    cols = {"pid": pad, "user": pad + 58, "s": pad + 124, "bar": pad + 150, "age": pad + 262, "cmd": pad + 316}
    d.add(f'<rect x="1" y="{top}" width="{W - 2}" height="{hh}" fill="#161616"/>')
    for k, label in [("pid", "PID"), ("user", "USER"), ("s", "S"), ("bar", "LAST PUSH"), ("age", "AGE"), ("cmd", "COMMAND")]:
        d.text(cols[k], top + 16, label, "mb", 10.5, ASH, ls=1)

    def T(x, y, txt, font, size, fill, anchor="start", ls=0):
        d.chars[font].update(txt)
        a_ = f' text-anchor="{anchor}"' if anchor != "start" else ""
        l_ = f' letter-spacing="{ls}"' if ls else ""
        return f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" fill="{fill}"{a_}{l_}>{esc(txt)}</text>'

    name_w = max(measure("ob", r["name"], 13, 1) for r in rows)

    def row(i, r, inv):
        y = body + i * rh
        base = y + rh / 2 + 4.5
        fg, dim, mid = ("#000", "#000", "#000") if inv else (SIGNAL, SMOKE, ASH)
        out = [T(cols["pid"], base, str(r["pid"]), "mr", 12, dim if not inv else fg),
               T(cols["user"], base, "root" if r["private"] else "nithin", "mr", 12, mid)]
        state = "R" if r["private"] or (r["age"] is not None and r["age"] <= 7) else "S"
        out.append(T(cols["s"], base, state, "mb", 12, fg if state == "R" else dim))
        bx, seg = cols["bar"], 11
        if r["private"]:  # classified: the meter is redacted
            out.append(f'<rect x="{bx}" y="{y + 11}" width="{8 * seg - 3}" height="14" fill="{fg if inv else "#2a2a2a"}"/>')
            out.append(T(bx + (8 * seg - 3) / 2, base, "REDACTED", "mb", 9, "#fff" if inv else ASH, "middle", 1.5))
            age = "—"
        else:
            fill = max(1 if r["age"] <= 120 else 0, 8 - round(r["age"] / 11))
            for k in range(8):
                on = k < fill
                col = (fg if on else "#555") if inv else (SIGNAL if on else "#222")
                out.append(f'<rect x="{bx + k * seg}" y="{y + 11}" width="{seg - 3}" height="14" fill="{col}"/>')
            age = "today" if r["age"] == 0 else f"{r['age']}d" if r["age"] < 60 else f"{r['age'] // 30}mo"
        out.append(T(cols["age"], base, age, "mr", 12, mid))
        out.append(T(cols["cmd"], base + 0.5, r["name"], "ob", 13, fg, ls=1))
        dx = cols["cmd"] + name_w + 18
        cw = measure("mb", r["chip"], 9.5, 1.5) + 14
        room = W - pad - cw - 16 - dx
        desc = r["desc"]
        while measure("mr", desc, 11.5) > room:
            desc = desc[:-2].rstrip(" ,.;:") + "…"
        out.append(T(dx, base, desc, "mr", 11.5, mid if inv else SMOKE))
        cx = W - pad - cw
        if r["private"]:
            out.append(f'<rect x="{cx:.1f}" y="{y + 10}" width="{cw:.1f}" height="16" fill="{"#000" if inv else SIGNAL}"/>')
            out.append(T(cx + cw / 2, y + 22, r["chip"], "mb", 9.5, "#fff" if inv else "#000", "middle", 1.5))
        else:
            out.append(f'<rect x="{cx:.1f}" y="{y + 10.5}" width="{cw:.1f}" height="15" fill="none" stroke="{fg if inv else SMOKE}"/>')
            out.append(T(cx + cw / 2, y + 22, r["chip"], "mr", 9.5, fg if inv else ASH, "middle", 1.5))
        return "".join(out)

    for i, r in enumerate(rows):
        if i:
            d.add(f'<path d="M{pad},{body + i * rh} H{W - pad}" stroke="#141414"/>')
        d.add(row(i, r, False))

    # htop's selection bar: an inverted row stepping down the process list
    ys = ";".join(str(body + i * rh) for i in range(len(rows)))
    d.defs.append(f'<clipPath id="selc"><rect x="1" y="{body}" width="{W - 2}" height="{rh}">'
                  f'<animate attributeName="y" values="{ys}" dur="{len(rows) * 1.4:.1f}s" calcMode="discrete" '
                  f'repeatCount="indefinite"/></rect></clipPath>')
    d.add(f'<g class="sel" clip-path="url(#selc)"><rect x="1" y="{body}" width="{W - 2}" height="{len(rows) * rh}" '
          f'fill="{SIGNAL}"/>{"".join(row(i, r, True) for i, r in enumerate(rows))}</g>')

    # the function-key bar along the bottom
    fy = H - 30
    d.add(f'<path d="M1,{fy - 4} H{W - 1}" stroke="{EDGE}"/>')
    x = pad
    for key, act in [("F1", "Help"), ("F2", "Setup"), ("F3", "Search"), ("F5", "Tree"), ("F6", "SortBy"),
                     ("F9", "Kill"), ("F10", "Quit")]:
        kw = measure("mb", key, 11) + 8
        d.add(f'<rect x="{x}" y="{fy + 2}" width="{kw:.1f}" height="17" fill="{SIGNAL}"/>')
        d.text(x + 4, fy + 15, key, "mb", 11, VOID)
        d.text(x + kw + 5, fy + 15, act, "mr", 11, ASH)
        x += kw + 5 + measure("mr", act, 11) + 20
    d.css.append(REDUCED.replace(".pulse,.beam{display:none}", ".pulse,.beam,.sel{display:none}"))
    d.save("ops.svg")


# ── telemetry (self-hosted, so ad blockers and dead stat services can't blank it) ──
USER = "nithin2719-commits"


def _get(url, as_json=True):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "readme-build"}
    if os.environ.get("GITHUB_TOKEN") and url.startswith("https://api.github.com"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    return json.loads(raw) if as_json else raw


def telemetry_data():
    cache = HERE / "telemetry.json"
    try:
        html = _get(f"https://github.com/users/{USER}/contributions", as_json=False)
        counts = {}
        for m in re.finditer(r'<tool-tip[^>]*for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)</tool-tip>', html):
            n = m.group(2).split()[0].replace(",", "")
            counts[m.group(1)] = 0 if n == "No" else int(n)
        days = []
        for m in re.finditer(r'<td[^>]*class="ContributionCalendar-day"[^>]*>', html):
            tag = m.group(0)
            date = re.search(r'data-date="([^"]+)"', tag).group(1)
            cid = re.search(r'id="(contribution-day-component-(\d+)-(\d+))"', tag)
            level = int(re.search(r'data-level="(\d)"', tag).group(1))
            days.append({"date": date, "row": int(cid.group(2)), "col": int(cid.group(3)),
                         "level": level, "count": counts.get(cid.group(1), 0)})
        days.sort(key=lambda d: d["date"])
        repos = [r for r in _get(f"https://api.github.com/users/{USER}/repos?per_page=100") if not r["fork"]]
        langs = {}
        for r in repos:
            if r["language"]:
                langs[r["language"]] = langs.get(r["language"], 0) + 1
        data = {"synced": dt.date.today().isoformat(), "days": days, "langs": langs, "repos": len(repos)}
        cache.write_text(json.dumps(data))
    except Exception as e:  # offline: reuse the last snapshot
        print(f"  ! telemetry fetch failed ({e}); using {cache.name}")
        data = json.loads(cache.read_text())
    return data


def _fmt(date):
    d = dt.date.fromisoformat(date)
    return f"{d:%b} {d.day}"


def telemetry():
    t = telemetry_data()
    days = t["days"]
    total = sum(d["count"] for d in days)

    runs, start = [], None  # (length, first, last) of every streak
    for i, d in enumerate(days):
        if d["count"]:
            start = i if start is None else start
        elif start is not None:
            runs.append((i - start, days[start]["date"], days[i - 1]["date"])); start = None
    if start is not None:
        runs.append((len(days) - start, days[start]["date"], days[-1]["date"]))
    longest = max(runs, default=(0, "", ""))
    # today still counts toward the streak until it's over
    tail = days[:-1] if days and not days[-1]["count"] else days
    current = next((n for n, _, last in reversed(runs) if last == tail[-1]["date"]), 0) if tail else 0
    peak = max(days, key=lambda d: d["count"])

    W, H = 1000, 0  # height is settled once every section is laid out
    d = Doc(W, H, f"{total} contributions in the last year; longest streak {longest[0]} days")

    stats = [
        (f"{total:,}", "contributions", "last 12 months"),
        (str(longest[0]), "longest streak", f"{_fmt(longest[1])} – {_fmt(longest[2])}" if longest[0] else "—"),
        (str(current), "current streak", "days running"),
        (str(peak["count"]), "peak day", _fmt(peak["date"])),
    ]
    col = (W - 72) / 4
    for i, (num, label, sub) in enumerate(stats):
        x = 36 + i * col + (14 if i else 0)
        if i:
            d.add(f'<path d="M{36 + i * col:.0f},40 V128" stroke="{EDGE}"/>')
        d.text(x, 84, num, "ob", 40, SIGNAL, ls=1)
        d.text(x, 108, label, "mr", 13, ASH)
        d.text(x, 126, sub, "mr", 11.5, SMOKE)
    d.add(f'<path d="M36,156 H{W - 36}" stroke="{GRID}"/>')
    pulse(d, f"M36,156 H{W - 36}", W - 72, "r1", 7, 1.4, 0.35, dash=90)

    # vitals monitor: the last 90 days as an ECG trace that keeps redrawing itself
    win = days[-90:]
    hi = max(x["count"] for x in win) or 1
    avg = sum(x["count"] for x in win) / len(win)
    wpk = max(win, key=lambda x: x["count"])
    px0, px1, ptop, pbot = 36, 792, 196, 334
    d.text(36, 182, "vitals  //  daily commits, last 90 days", "mr", 11.5, SMOKE)
    grid = []
    for gx_ in range(px0, px1 + 1, 12):
        grid.append(f'<path d="M{gx_},{ptop} V{pbot}" stroke="{"#1a1a1a" if (gx_ - px0) % 60 == 0 else "#0d0d0d"}"/>')
    for gy_ in range(pbot, ptop - 1, -12):
        grid.append(f'<path d="M{px0},{gy_} H{px1}" stroke="{"#1a1a1a" if (pbot - gy_) % 60 == 0 else "#0d0d0d"}"/>')
    d.add("".join(grid))
    step = (px1 - px0) / (len(win) - 1)
    pts = [(px0 + i * step, pbot - 6 - (x["count"] / hi) ** 0.5 * (pbot - ptop - 22)) for i, x in enumerate(win)]
    curve = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):  # catmull-rom → bezier, clamped so it never dips under the baseline
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(pbot - 6, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(pbot - 6, p2[1] - (p3[1] - p1[1]) / 6))
        curve += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    d.defs.append('<linearGradient id="wf" x1="0" y1="0" x2="0" y2="1">'
                  '<stop offset="0" stop-color="#fff" stop-opacity=".18"/>'
                  '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    d.add(f'<path d="{curve} L{px1},{pbot} L{px0},{pbot} Z" fill="url(#wf)"/>')
    d.add(f'<path d="{curve}" fill="none" stroke="#3d3d3d" stroke-width="1.4"/>')
    glow(d)
    period, draw = 7, 0.72
    d.add(f'<path d="{curve}" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round" pathLength="1000" '
          f'stroke-dasharray="1000" stroke-dashoffset="0" filter="url(#glow)">'
          f'<animate attributeName="stroke-dashoffset" values="1000;0;0" keyTimes="0;{draw};1" dur="{period}s" '
          f'repeatCount="indefinite"/></path>')
    d.add(f'<circle r="5" fill="#fff" filter="url(#glow)">'
          f'<animateMotion dur="{period}s" repeatCount="indefinite" path="{curve}" keyPoints="0;1;1" '
          f'keyTimes="0;{draw};1" calcMode="linear"/>'
          f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;{draw - 0.01:.2f};{draw};1" dur="{period}s" '
          f'repeatCount="indefinite"/></circle>')
    kx, ky = pts[win.index(wpk)]
    d.add(f'<circle cx="{kx:.1f}" cy="{ky:.1f}" r="3.5" fill="{SIGNAL}"/>')
    d.text(kx, ky - 10, str(wpk["count"]), "mr", 10.5, ASH, "middle")
    for i in (0, len(win) // 2, len(win) - 1):
        anchor = "start" if i == 0 else "end" if i == len(win) - 1 else "middle"
        d.text(pts[i][0], pbot + 17, _fmt(win[i]["date"]).lower(), "mr", 10.5, SMOKE, anchor)

    # monitor readout, right of the trace
    rx = px1 + 26
    d.add(f'<path d="M{px1 + 12},{ptop} V{pbot}" stroke="{EDGE}"/>')
    d.text(rx, ptop + 14, "AVG / DAY", "mb", 10.5, SMOKE, ls=2)
    d.text(rx, ptop + 62, f"{avg:.1f}", "ob", 44, SIGNAL, ls=1)
    d.add(f'<rect class="now" x="{W - 80}" y="{ptop + 5}" width="8" height="8" fill="{SIGNAL}"/>')
    d.text(W - 36, ptop + 13.5, "LIVE", "mb", 10.5, ASH, "end", 2)
    d.text(rx, ptop + 98, "PEAK", "mb", 10.5, SMOKE, ls=2)
    d.text(rx, ptop + 126, str(wpk["count"]), "ob", 24, SIGNAL, ls=1)
    d.text(rx + measure("ob", str(wpk["count"]), 24, 1) + 10, ptop + 126, _fmt(wpk["date"]).lower(), "mr", 11, SMOKE)
    d.add(f'<path d="M36,366 H{W - 36}" stroke="{GRID}"/>')
    pulse(d, f"M{W - 36},366 H36", W - 72, "r3", 7, 2.6, 0.35, dash=90)

    # heatmap
    cols = max(x["col"] for x in days) + 1
    gutter = 40
    pitch = int((W - 72 - gutter) / cols)
    cell = pitch - 3
    gx = 36 + gutter + (W - 72 - gutter - cols * pitch + 3) / 2
    gy = 410
    shades = ["#161616", "#3d3d3d", "#707070", "#a8a8a8", SIGNAL]
    seen = set()
    colg = {}
    for x in days:
        dd = dt.date.fromisoformat(x["date"])
        if x["row"] == 0 and dd.day <= 7 and (dd.month, dd.year) not in seen and x["col"] < cols - 1:
            seen.add((dd.month, dd.year))
            d.text(gx + x["col"] * pitch, gy - 10, f"{dd:%b}".lower(), "mr", 11, SMOKE)
        cls = ' class="now"' if x is days[-1] else ""
        colg.setdefault(x["col"], []).append(
            f'<rect x="{gx + x["col"] * pitch:.1f}" y="{gy + x["row"] * pitch}" width="{cell}" '
            f'height="{cell}" fill="{shades[x["level"]]}"{cls}/>')
    for c, rects in sorted(colg.items()):
        d.add(f'<g class="hc" style="animation-delay:{0.2 + c * 0.018:.3f}s">{"".join(rects)}</g>')
    for r, name in [(1, "mon"), (3, "wed"), (5, "fri")]:
        d.text(36, gy + r * pitch + cell - 2, name, "mr", 10.5, SMOKE)
    ly = gy + 7 * pitch + 18
    lx = W - 36 - 5 * (cell + 3) - measure("mr", "more", 11) - 8
    d.text(lx - 8, ly, "less", "mr", 11, SMOKE, "end")
    for i, c in enumerate(shades):
        d.add(f'<rect x="{lx + i * (cell + 3):.1f}" y="{ly - cell + 2}" width="{cell}" height="{cell}" fill="{c}"/>')
    d.text(lx + 5 * (cell + 3) + 5, ly, "more", "mr", 11, SMOKE)
    d.add(f'<path d="M36,{ly + 22} H{W - 36}" stroke="{GRID}"/>')
    pulse(d, f"M{W - 36},{ly + 22} H36", W - 72, "r2", 7, 3.9, 0.35, dash=90)

    # primary language per original repo
    langs = sorted(t["langs"].items(), key=lambda kv: -kv[1])
    n = sum(v for _, v in langs)
    by = ly + 54
    d.text(36, by, f"primary language of {n} original repos", "mr", 11.5, SMOKE)
    d.text(W - 36, by, f"synced {t['synced']}", "mr", 11.5, SMOKE, "end")
    tones = [SIGNAL, "#bdbdbd", "#8a8a8a", "#5e5e5e", "#3d3d3d", "#2a2a2a"]
    x, bw = 36.0, W - 72
    for i, (name, v) in enumerate(langs):
        w = bw * v / n
        d.add(f'<rect x="{x:.1f}" y="{by + 14}" width="{max(w - 2, 1):.1f}" height="10" fill="{tones[min(i, 5)]}"/>')
        x += w
    x = 36.0
    for i, (name, v) in enumerate(langs):
        d.add(f'<rect x="{x:.1f}" y="{by + 40}" width="9" height="9" fill="{tones[min(i, 5)]}"/>')
        label = f"{name.lower()} {100 * v / n:.0f}%"
        d.text(x + 15, by + 49, label, "mr", 12, ASH if i == 0 else SMOKE)
        x += measure("mr", label, 12) + 40

    d.css.append(".hc{animation:boot .35s linear both}"
                 "@keyframes boot{0%{opacity:0}50%{opacity:1}65%{opacity:.4}100%{opacity:1}}"
                 ".now{animation:blink 1.1s steps(1) infinite;stroke:#fff;stroke-width:1.5}"
                 "@keyframes blink{50%{opacity:.15}}" + REDUCED)
    H = int(by + 49 + 32)
    d.h = H
    d.parts.insert(0, f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=24, bl=24)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.save("telemetry.svg")


# ── footer ───────────────────────────────────────────────────────────────────
def footer():
    W, H = 1200, 344
    d = Doc(W, H, "Nah, I'd hack.")
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=30, bl=30)}" fill="{VOID}" stroke="{EDGE}"/>')
    glow(d, std=3.2)
    d.defs.append(BLADE_GRADIENT)
    d.defs.append('<filter id="neon" x="-20%" y="-60%" width="140%" height="220%">'
                  '<feGaussianBlur stdDeviation="7" result="b"/>'
                  '<feComponentTransfer in="b" result="s"><feFuncA type="linear" slope=".6"/></feComponentTransfer>'
                  '<feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    d.text(W / 2, 92, "NAH, I'D HACK.", "ob", 36, SIGNAL, "middle", 9)

    # the line rises into BlackArch's glowing "A"; the katana passes straight through it
    c, size, y = W / 2, 114, 300
    apex = y - size
    outline = arch_pts(ARCH_A, c, y, size)
    ridge = arch_pts(ARCH_RIDGE, c, y, size)
    left, right = ridge[0][0], ridge[-1][0]
    d.add(f'<path d="M60,{y} H{left:.1f} M{right:.1f},{y} H{W - 60}" stroke="{EDGE}"/>')
    d.add(f'<polygon points="{fmt_pts(outline)}" fill="none" stroke="#cfcfcf" stroke-width="2.2" '
          f'stroke-linejoin="round" filter="url(#glow)"/>')
    d.defs.append(katana_defs(c, apex, size))
    d.add(katana(c, apex, size))

    # one bright pulse: in along the line, up and over the A, out the other side
    route = [(60, y)] + ridge + [(W - 60, y)]
    plen = sum(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 for (ax, ay), (bx, by) in zip(route, route[1:]))
    d.add(f'<polyline class="pulse" points="{fmt_pts(route)}" fill="none" stroke="{SIGNAL}" stroke-width="3" '
          f'stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="90 {plen:.0f}" filter="url(#glow)"/>')
    d.css.append(f".pulse{{animation:pulse 5s linear infinite}}"
                 f"@keyframes pulse{{from{{stroke-dashoffset:90}}to{{stroke-dashoffset:-{plen:.0f}}}}}" + REDUCED)
    d.text(60, y - 14, "logout", "mr", 14, SMOKE)
    d.text(W - 60, y - 14, "connection to nithin@blackarch closed.", "mr", 14, SMOKE, "end")
    d.save("footer.svg")


if __name__ == "__main__":
    if "--live" in sys.argv or "--telemetry" in sys.argv:  # what the hourly refresh job runs
        telemetry()
        ops()
        sys.exit()
    print("building assets →", OUT)
    hero()
    ticker()
    for i, (slug, title, note) in enumerate([
        ("whoami", "WHOAMI", "uid=0(nithin) gid=0(root) groups=ctf"),
        ("arsenal", "ARSENAL", "pacman -Sg blackarch | wc -l"),
        ("ops", "OPERATIONS", "ls -la ~/ops"),
        ("telemetry", "TELEMETRY", "tail -f /var/log/commits"),
        ("uplink", "UPLINK", "nc -lvnp 1337"),
    ]):
        header(slug, title, note, delay=i * 1.3)
    fetch()
    arsenal()
    ops()
    telemetry()
    for slug, ico, name, handle in [
        ("github", "github", "GITHUB", "nithin2719-commits"),
        ("linkedin", "linkedin", "LINKEDIN", "nithin-g"),
        ("ig", "instagram", "INSTAGRAM", "@nit_2719"),
    ]:
        chip(slug, ico, name, handle)
    footer()
