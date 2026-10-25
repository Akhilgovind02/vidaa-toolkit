#!/usr/bin/env python3
"""Generate demo.gif — a terminal-style animated demo of the vidaa CLI. Controlled content; no real device data."""
from PIL import Image, ImageDraw, ImageFont

W, H = 900, 320
BG = (13, 17, 23)
BAR = (22, 27, 34)
WHITE = (230, 237, 243)
GREEN = (63, 185, 80)
DIM = (139, 148, 158)
CYAN = (86, 211, 229)
FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 19, index=0)
FB = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14, index=0)
LH = 27
X0, Y0 = 24, 54

SCRIPT = [
    ("cmd", "vidaa state"),
    ("out", '{"statetype":"app","name":"netflix","url":"netflix"}', CYAN),
    ("hold", 16), ("gap",),
    ("cmd", "vidaa key KEY_VOLUMEUP KEY_VOLUMEDOWN"),
    ("out", "sent: KEY_VOLUMEUP KEY_VOLUMEDOWN", GREEN),
    ("hold", 16), ("gap",),
    ("cmd", "vidaa launch http://192.168.1.50:8099/"),
    ("out", "launched: http://192.168.1.50:8099/", GREEN),
    ("out", '192.168.1.50 - "GET / HTTP/1.1" 200   # the TV fetched your page', DIM),
    ("hold", 40),
]

lines = []
frames = []
durs = []

def render(cursor_line=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 36], fill=BAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([18 + i * 22, 12, 30 + i * 22, 24], fill=c)
    d.text((W // 2 - 50, 10), "vidaa-toolkit", font=FB, fill=DIM)
    y = Y0
    for segs in lines + ([cursor_line] if cursor_line else []):
        x = X0
        for text, color in segs:
            d.text((x, y), text, font=FONT, fill=color)
            x += d.textlength(text, font=FONT)
        y += LH
    frames.append(img)

for ev in SCRIPT:
    if ev[0] == "cmd":
        txt = ev[1]
        for i in range(len(txt) + 1):
            cur = [("$ ", GREEN), (txt[:i], WHITE), ("█" if i < len(txt) else "", WHITE)]
            render(cur); durs.append(45)
        lines.append([("$ ", GREEN), (txt, WHITE)])
        render(); durs.append(120)
    elif ev[0] == "out":
        lines.append([(ev[1], ev[2])])
        render(); durs.append(500)
    elif ev[0] == "gap":
        lines.append([("", DIM)])
    elif ev[0] == "hold":
        render(); durs.append(45 * ev[1])

render(); durs.append(2200)
frames[0].save("demo.gif", save_all=True, append_images=frames[1:], duration=durs, loop=0, optimize=True)
print(f"demo.gif written: {len(frames)} frames")
