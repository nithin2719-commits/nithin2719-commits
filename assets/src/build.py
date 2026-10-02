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
import re
import pathlib
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
    return instancer.instantiateVariableFont(TTFont(_source(name)), {"wght": weight})


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
    sub = TTFont(buf)
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
    # the BlackArch sword
    "blackarch": '<path d="M12 0 14.9 3.4V14.2H9.1V3.4Z"/><path d="M4.6 14.2H19.4V17H4.6Z"/>'
                 '<path d="M10.6 17H13.4V20.8H10.6Z"/><circle cx="12" cy="21.8" r="2.2"/>',
    # radar sweep for nmap
    "nmap": '<g fill="none" stroke="#fff" stroke-width="1.8"><circle cx="12" cy="12" r="10"/>'
            '<circle cx="12" cy="12" r="5.5"/><path d="M12 12 19.2 4.8" stroke-width="2.2"/></g>'
            '<circle cx="12" cy="12" r="1.9"/><circle cx="16.6" cy="15.4" r="1.5"/>',
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


def icon(slug, x, y, size, fill=SIGNAL):
    inner = CUSTOM_ICONS.get(slug) or f'<path d="{icon_path(slug)}"/>'
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


REDUCED = "@media (prefers-reduced-motion:reduce){*{animation:none!important}.g,.gl,.pre,.scan{display:none}.f,.late,.t,.ln,.hc{opacity:1!important}.fl,.kx,.pulse{display:none}.mq{transform:none!important}}"


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

    # prompt line + status that flips once the name resolves
    prompt = "root@blackarch:~# ./decrypt --target nithin"
    d.text(52, 62, prompt, "mr", 15, ASH)
    cx = 52 + measure("mr", prompt, 15) + 8
    d.add(f'<rect class="cur" x="{cx:.1f}" y="49" width="9" height="17" fill="{SIGNAL}"/>')
    d.text(W - 52, 62, "DECRYPTING …", "mr", 13, SMOKE, "end", 2, "pre")
    d.text(W - 52, 62, "ACCESS GRANTED", "mb", 13, SIGNAL, "end", 2, "f late", ' style="animation-delay:1.55s"')

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
                 ".ln{opacity:0;animation:on .01s linear forwards}@keyframes on{to{opacity:1}}" + REDUCED)
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
    W, pad, rh, gap, top = 1000, 24, 92, 10, 60
    H = top + len(ARSENAL) * (rh + gap) - gap + pad
    count = sum(1 for _, tools in ARSENAL for t in tools if t)
    d = Doc(W, H, "Arsenal: " + ", ".join(t[1] for _, tools in ARSENAL for t in tools if t))
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=24, bl=24)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.add(f'<path d="M0.5,40 H{W - 0.5}" stroke="{EDGE}"/>')
    d.text(pad, 25, "/opt/arsenal", "mr", 12, SMOKE)
    d.text(W - pad - 4, 25, "loading modules …", "mr", 12, SMOKE, "end", cls="pre")
    msg = f"{count} modules online"
    d.text(W - pad - 4, 25, msg, "mr", 12, ASH, "end", cls="f late", extra=' style="animation-delay:1.5s"')
    d.add(f'<rect class="f late" style="animation-delay:1.5s" x="{W - pad - 18 - measure("mr", msg, 12):.1f}" '
          f'y="16" width="8" height="8" fill="{SIGNAL}"/>')

    cat_w = 146
    x0 = pad + cat_w + gap
    tw = (W - pad - x0 - 5 * gap) / 6
    k = 0
    for r, ((l1, l2), tools) in enumerate(ARSENAL):
        y = top + r * (rh + gap)
        d.add(f'<rect x="{pad}" y="{y}" width="3" height="{rh}" fill="{SIGNAL}"/>')
        d.text(pad + 16, y + 32, l1, "ob", 14, SIGNAL, ls=1.5)
        if l2:
            d.text(pad + 16, y + 51, l2, "ob", 14, SIGNAL, ls=1.5)
        d.text(pad + 16, y + rh - 14, f"{sum(1 for t in tools if t):02d} modules", "mr", 11, SMOKE)
        for c, tool in enumerate(tools):
            x = x0 + c * (tw + gap)
            shape = chamfer(x + 0.5, y + 0.5, tw - 1, rh - 1, tr=10)
            if tool is None:
                d.add(f'<path d="{shape}" fill="none" stroke="{SMOKE}" stroke-dasharray="4 4"/>')
                d.text(x + tw / 2, y + 44, "+", "ob", 22, SMOKE, "middle")
                d.text(x + tw / 2, y + 70, "slot open", "mr", 10.5, SMOKE, "middle")
                continue
            slug, name, role = tool
            label = name.upper()
            size = min(11.5, 11.5 * (tw - 28) / measure("om", label, 11.5, 1))
            delay = 0.25 + k * 0.045
            k += 1
            inner = (f'<path d="{shape}" fill="{VOID}" stroke="{EDGE}"/>'
                     + icon(slug, x + 14, y + 14, 22)
                     + f'<rect x="{x + tw - 24:.1f}" y="{y + 15}" width="5" height="5" fill="{SIGNAL}"/>')
            d.chars["om"].update(label); d.chars["mr"].update(role)
            inner += (f'<text x="{x + 14:.1f}" y="{y + 64}" font-family="om" font-size="{size:.2f}" '
                      f'letter-spacing="1" fill="{SIGNAL}">{esc(label)}</text>'
                      f'<text x="{x + 14:.1f}" y="{y + 80}" font-family="mr" font-size="10.5" '
                      f'fill="{ASH}">{esc(role)}</text>')
            d.add(f'<g class="t" style="animation-delay:{delay:.2f}s">{inner}</g>')
            d.add(f'<path class="fl" style="animation-delay:{delay:.2f}s" d="{shape}" fill="none" '
                  f'stroke="{SIGNAL}" stroke-width="1.5"/>')

    d.defs.append('<linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">'
                  '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                  '<stop offset=".85" stop-color="#fff" stop-opacity=".07"/>'
                  '<stop offset="1" stop-color="#fff" stop-opacity=".22"/></linearGradient>')
    d.add(f'<rect class="scan" x="1" y="-70" width="{W - 2}" height="70" fill="url(#sg)"/>')
    d.css.append(
        ".t{animation:boot .5s linear both}"
        "@keyframes boot{0%,40%{opacity:.07}42%{opacity:1}55%{opacity:.3}68%,100%{opacity:1}}"
        ".fl{opacity:0;animation:flash .6s ease-out both}@keyframes flash{0%{opacity:0}35%{opacity:1}100%{opacity:0}}"
        ".f{opacity:0;animation:lock .01s linear forwards}@keyframes lock{to{opacity:1}}"
        ".pre{animation:gone .01s linear 1.5s forwards}@keyframes gone{to{opacity:0}}"
        f".scan{{animation:scan 7s linear 1.8s infinite}}"
        f"@keyframes scan{{0%{{transform:translateY(40px)}}45%,100%{{transform:translateY({H + 70}px)}}}}"
        + REDUCED)
    d.save("arsenal.svg")


# ── live-feed ticker under the hero ─────────────────────────────────────────
FEED = ["[+] uplink established", "operator: nithin", "loc: india", "os: blackarch linux",
        "focus: offensive security", "now building: KRYPT", "now learning: malware analysis",
        "ctf: hackthebox / tryhackme", "[!] if it's connected, it's vulnerable"]


def ticker():
    W, H = 1000, 40
    d = Doc(W, H, "Live feed: " + " / ".join(FEED))
    d.add(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" fill="{VOID}" stroke="{EDGE}"/>')
    tag = "LIVE FEED"
    cw = measure("om", tag, 11, 2) + 44
    d.add(f'<path d="{chamfer(0, 0, cw, H, br=12)}" fill="{SIGNAL}"/>')
    d.add(f'<rect class="cur" x="14" y="16" width="8" height="8" fill="{VOID}"/>')
    d.text(30, 24.5, tag, "om", 11, VOID, ls=2)

    sep = "   ///   "
    spans, plain = "", ""
    for item in FEED:
        hot = item.startswith("[")
        spans += f'<tspan fill="{SIGNAL if hot else ASH}">{esc(item)}</tspan><tspan fill="{SMOKE}">{sep}</tspan>'
        plain += item + sep
    d.chars["mr"].update(plain)
    L = measure("mr", plain, 12.5)
    d.defs.append(f'<clipPath id="tk"><rect x="{cw + 4:.0f}" y="0" width="{W - cw - 5:.0f}" height="{H}"/></clipPath>')
    row = "".join(f'<text x="{cw + 18 + i * L:.1f}" y="25" font-family="mr" font-size="12.5">{spans}</text>' for i in range(3))
    d.add(f'<g clip-path="url(#tk)"><g class="mq">{row}</g></g>')
    d.css.append(f".mq{{animation:mq {L / 48:.1f}s linear infinite}}@keyframes mq{{to{{transform:translateX(-{L:.1f}px)}}}}"
                 ".cur{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}" + REDUCED)
    d.save("ticker.svg")


# ── uplink chips + visitor label ────────────────────────────────────────────
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


def visitors_label():
    text = "VISITORS"
    W, H = round(measure("om", text, 11, 2) + 40), 28
    d = Doc(W, H, "Visitors")
    d.add(f'<rect width="{W}" height="{H}" fill="{VOID}"/>')
    d.add(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" fill="none" stroke="{SIGNAL}"/>')
    d.add(f'<rect x="12" y="10" width="8" height="8" fill="{SIGNAL}"/>')
    d.text(28, 18.5, text, "om", 11, SIGNAL, ls=2)
    d.save("l-visitors.svg")


# ── project cards ────────────────────────────────────────────────────────────
def wrap(text, n):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + (1 if cur else 0) > n:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + [cur]


def card(slug, kind, title, desc, tags, chip, private=False):
    W, H = 480, 210
    d = Doc(W, H, f"{title}: {desc}")
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=20)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.add(bracket(W - 0.5 - 1, H - 0.5 - 1, 16, -1, -1))
    d.text(26, 36, kind, "mr", 11, SMOKE, ls=2)

    cw = measure("mb", chip, 11, 1.5) + 18
    if private:
        d.add(f'<rect x="{W - 34 - cw:.1f}" y="22" width="{cw:.1f}" height="20" fill="{SIGNAL}"/>')
        d.text(W - 34 - cw / 2, 36, chip, "mb", 11, VOID, "middle", 1.5)
    else:
        d.add(f'<rect x="{W - 34 - cw:.1f}" y="22.5" width="{cw:.1f}" height="19" fill="none" stroke="{SMOKE}"/>')
        d.text(W - 34 - cw / 2, 36, chip, "mr", 11, ASH, "middle", 1.5)

    if private:  # an encrypted name that flickers through ciphertext now and then
        d.text(26, 80, title, "ob", 25, SIGNAL, ls=2, cls="kt")
        d.text(26, 80, "K#Y?7", "ob", 25, SIGNAL, ls=2, cls="kx")
        d.text(26, 80, "%R/PT", "ob", 25, ASH, ls=2, cls="kx kx2")
        d.css.append(".kx{opacity:0;animation:kx 6s steps(1) 2s infinite}.kx2{animation-name:kx2}"
                     ".kt{animation:kt 6s steps(1) 2s infinite}"
                     "@keyframes kt{0%{opacity:1}92%{opacity:0}97%{opacity:1}}"
                     "@keyframes kx{0%{opacity:0}92%{opacity:1}94.5%{opacity:0}}"
                     "@keyframes kx2{0%{opacity:0}94.5%{opacity:1}97%{opacity:0}}" + REDUCED)
    else:
        d.text(26, 80, title, "ob", 25, SIGNAL, ls=2)
    for i, line in enumerate(wrap(desc, 54)[:3]):
        d.text(26, 110 + i * 19, line, "mr", 13, ASH)
    d.add(f'<path d="M26,{H - 44} H{W - 26}" stroke="{GRID}"/>')
    d.text(26, H - 21, "  /  ".join(tags), "mr", 11.5, SMOKE)
    d.save(f"p-{slug}.svg")


# ── telemetry (self-hosted, so ad blockers and dead stat services can't blank it) ──
USER = "nithin2719-commits"


def _get(url, as_json=True):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "readme-build"})
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

    W, H = 1000, 470
    d = Doc(W, H, f"{total} contributions in the last year; longest streak {longest[0]} days")
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=24, bl=24)}" fill="{VOID}" stroke="{EDGE}"/>')

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

    # heatmap
    cols = max(x["col"] for x in days) + 1
    gutter = 40
    pitch = int((W - 72 - gutter) / cols)
    cell = pitch - 3
    gx = 36 + gutter + (W - 72 - gutter - cols * pitch + 3) / 2
    gy = 200
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

    # primary language per original repo
    langs = sorted(t["langs"].items(), key=lambda kv: -kv[1])
    n = sum(v for _, v in langs)
    by = ly + 52
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
    d.h = H
    d.save("telemetry.svg")


# ── footer ───────────────────────────────────────────────────────────────────
def footer():
    W, H = 1200, 210
    d = Doc(W, H, "The quieter you become, the more you hear.")
    d.add(f'<path d="{chamfer(0.5, 0.5, W - 1, H - 1, tr=30, bl=30)}" fill="{VOID}" stroke="{EDGE}"/>')
    d.text(W / 2, 82, "THE QUIETER YOU BECOME,", "om", 22, SIGNAL, "middle", 7)
    d.text(W / 2, 116, "THE MORE YOU HEAR.", "om", 22, SIGNAL, "middle", 7)

    # a flat line with a single small signal in it
    y, c = 162, W / 2
    pts = [(60, y), (c - 46, y), (c - 30, y - 4), (c - 18, y + 6), (c - 6, y - 22),
           (c + 6, y + 14), (c + 16, y - 6), (c + 26, y), (W - 60, y)]
    path = " ".join(f"{px:.0f},{py:.0f}" for px, py in pts[1:-1])
    d.add(f'<polyline points="{60},{y} {c - 46:.0f},{y}" fill="none" stroke="{EDGE}"/>')
    d.add(f'<polyline points="{c + 26:.0f},{y} {W - 60},{y}" fill="none" stroke="{EDGE}"/>')
    d.add(f'<polyline points="{path}" fill="none" stroke="{SIGNAL}" stroke-width="1.5"/>')
    full = [(60, y)] + pts[1:-1] + [(W - 60, y)]
    plen = sum(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 for (ax, ay), (bx, by) in zip(full, full[1:]))
    pl = " ".join(f"{px:.0f},{py:.0f}" for px, py in full)
    d.add(f'<polyline class="pulse" points="{pl}" fill="none" stroke="{SIGNAL}" stroke-width="2.5" '
          f'stroke-linecap="round" stroke-dasharray="70 {plen:.0f}"/>')
    d.css.append(f".pulse{{animation:pulse 4s linear infinite}}"
                 f"@keyframes pulse{{from{{stroke-dashoffset:70}}to{{stroke-dashoffset:-{plen:.0f}}}}}" + REDUCED)
    d.text(60, y - 14, "logout", "mr", 14, SMOKE)
    d.text(W - 60, y - 14, "connection to nithin@blackarch closed.", "mr", 14, SMOKE, "end")
    d.save("footer.svg")


if __name__ == "__main__":
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
    card("krypt", "CTF AUTOMATION", "KRYPT",
         "Autonomous CTF triage and flag hunter. Classifies the challenge, runs the right "
         "tools, carves and decodes recursively, then ranks every flag candidate.",
         ["python", "pwn", "rev", "stego", "crypto", "web"], "PRIVATE BUILD", private=True)
    card("toolbox", "OFFENSIVE TOOLING", "BLACKARCH TOOLBOX",
         "One keybinding to launch any of BlackArch's ~4000 security tools from a clean, "
         "searchable menu. Linux, macOS and WSL.",
         ["bash", "awk", "fzf-style menu"], "SHELL")
    card("agx", "AI AGENTS", "AGX",
         "An operations console for a team of autonomous coding agents that plan, build, "
         "review and commit across every project. Fully local.",
         ["python", "claude code", "agy", "scheduler"], "PYTHON")
    card("hypr", "ARCH RICE", "HYPRLAND-CONFIGS",
         "A graphite-monochrome Hyprland rice: custom Waybar, hand-written notification "
         "theme, eww dashboard and ROG hardware controls.",
         ["hyprland", "waybar", "eww"], "CSS")
    card("evidence", "DFIR", "EVIDENCEFLOW",
         "Browser-based digital forensics artifact workbench, built as an extension for "
         "PWNDORA.",
         ["forensics", "browser", "artifacts"], "FORK")
    card("medios", "SOFTWARE", "MEDIOS",
         "Offline pharmacy POS and inventory system. GST billing, batch and expiry tracking, "
         "Schedule H compliance, one-click backups.",
         ["python", "pos", "offline-first"], "PYTHON")
    telemetry()
    for slug, ico, name, handle in [
        ("github", "github", "GITHUB", "nithin2719-commits"),
        ("thm", "tryhackme", "TRYHACKME", "nithin2719"),
        ("htb", "hackthebox", "HACKTHEBOX", "nithin2719"),
        ("ig", "instagram", "INSTAGRAM", "@nit_2719"),
    ]:
        chip(slug, ico, name, handle)
    visitors_label()
    footer()
