"""Render the pipeline flow chart to PNG, for the deck and for checking.

Same coordinates as the inline SVG in docs/flow.html. Drawing it a second way
is also how the layout gets checked: the browser pane will not composite here,
so this is the only way to look at it.
"""

from __future__ import annotations

import os
import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).parent
OUT = HERE / "flow.png"
FONTS = pathlib.Path(os.environ["WINDIR"]) / "Fonts"

S = 2.2                      # scale from SVG units to pixels
VB_W, VB_H = 880, 1010
W, H = int(VB_W * S), int(VB_H * S)

GROUND = (250, 249, 247)
INK = (28, 26, 23)
SOFT = (107, 101, 96)
CODE = (22, 78, 91)
LLM = (154, 127, 82)
EXIT = (180, 83, 9)
OK = (21, 128, 61)


def blend(c, bg, a):
    return tuple(int(c[i] * a + bg[i] * (1 - a)) for i in range(3))


_fc: dict = {}


def f(size, bold=False, italic=False):
    key = (round(size, 1), bold, italic)
    if key in _fc:
        return _fc[key]
    name = "segoeuii.ttf" if italic else ("segoeuib.ttf" if bold else "segoeui.ttf")
    p = FONTS / name
    if not p.exists():
        p = FONTS / ("calibrib.ttf" if bold else "calibri.ttf")
    _fc[key] = ImageFont.truetype(str(p), max(int(size * S), 6))
    return _fc[key]


img = Image.new("RGB", (W, H), GROUND)
d = ImageDraw.Draw(img)


def box(x, y, w, h, color, alpha=0.13, width=1.6):
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=6 * S,
                        fill=blend(color, GROUND, alpha), outline=color,
                        width=max(int(width * S), 2))


def text(x, y, s, *, size=14, color=INK, bold=False, italic=False, anchor="mm"):
    d.text((x * S, y * S), s, font=f(size, bold, italic), fill=color, anchor=anchor)


def poly(points, color, width=1.5, arrow=True):
    pts = [(px * S, py * S) for px, py in points]
    d.line(pts, fill=color, width=max(int(width * S), 2), joint="curve")
    if arrow:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        n = (dx * dx + dy * dy) ** 0.5 or 1
        ux, uy = dx / n, dy / n
        a = 5.2 * S
        d.polygon([(x1, y1), (x1 - a * ux + a * 0.55 * uy, y1 - a * uy - a * 0.55 * ux),
                   (x1 - a * ux - a * 0.55 * uy, y1 - a * uy + a * 0.55 * ux)], fill=color)


FAINT = blend(INK, GROUND, 0.55)

# ---------------------------------------------------------------- diagram ---
box(150, 24, 300, 46, CODE)
text(300, 42, "Question", size=14, bold=True)
text(300, 59, "plus up to four previous turns", size=11.5, color=SOFT)

poly([(300, 70), (300, 102)], FAINT)

box(150, 104, 300, 62, LLM, alpha=0.20)
text(300, 122, "Query understanding", size=14, bold=True)
text(300, 139, "constrained JSON → intent, district", size=11.5, color=SOFT)
text(300, 155, "district re-spelled in Python, not trusted", size=11.5, color=SOFT)

poly([(300, 166), (300, 202)], FAINT)
text(306, 186, "structured intent", size=11, color=SOFT, italic=True, anchor="lm")

# refusal
poly([(450, 135), (532, 135), (532, 178), (556, 178)], EXIT)
poly([(450, 227), (532, 227), (532, 198), (556, 198)], EXIT)
box(560, 160, 270, 54, EXIT)
text(695, 180, "Refusal", size=14, bold=True)
text(695, 198, "names what it does cover", size=11.5, color=SOFT)
text(456, 127, "out of scope", size=11, color=SOFT, italic=True, anchor="lm")
text(456, 241, "no such district", size=11, color=SOFT, italic=True, anchor="lm")

box(150, 204, 300, 46, CODE)
text(300, 222, "Retrieval", size=14, bold=True)
text(300, 239, "a dictionary lookup on the intent — no model", size=11.5, color=SOFT)

poly([(240, 250), (240, 270), (195, 270), (195, 290)], FAINT)
poly([(360, 250), (360, 270), (405, 270), (405, 290)], FAINT)
text(186, 282, "how much water", size=11, color=SOFT, italic=True, anchor="rm")
text(414, 282, "quality · causes", size=11, color=SOFT, italic=True, anchor="lm")

box(110, 292, 170, 78, CODE)
text(195, 310, "PostgreSQL", size=14, bold=True)
text(195, 328, "36,879 readings", size=11.5, color=SOFT)
text(195, 344, "1,607 stations", size=11.5, color=SOFT)
text(195, 360, "exact, with a date", size=11.5, color=SOFT)

box(320, 292, 170, 78, CODE)
text(405, 310, "CGWB report", size=14, bold=True)
text(405, 328, "178 passages", size=11.5, color=SOFT)
text(405, 344, "dot product, then", size=11.5, color=SOFT)
text(405, 360, "rerank by district", size=11.5, color=SOFT)

poly([(195, 370), (195, 392), (300, 392), (300, 404)], FAINT)
poly([(405, 370), (405, 392), (300, 392)], FAINT, arrow=False)

box(150, 406, 300, 52, CODE)
text(300, 424, "Calculation", size=14, bold=True)
text(300, 442, "numpy projection + its caveats — projections only", size=11.5, color=SOFT)

poly([(300, 458), (300, 498)], FAINT)
text(306, 480, "figures, and a source for each", size=11, color=SOFT, italic=True, anchor="lm")

box(150, 500, 300, 52, LLM, alpha=0.20)
text(300, 518, "Response", size=14, bold=True)
text(300, 536, "writes prose around figures it was handed", size=11.5, color=SOFT)

poly([(300, 552), (300, 592)], FAINT)
text(306, 574, "draft", size=11, color=SOFT, italic=True, anchor="lm")

poly([(450, 526), (520, 526), (520, 836), (556, 836)], EXIT)
text(456, 518, "unparsable ×3", size=11, color=SOFT, italic=True, anchor="lm")

box(150, 594, 300, 74, CODE)
text(300, 612, "Eight checks — blocking", size=14, bold=True)
text(300, 630, "citations · figures · districts · years", size=11.5, color=SOFT)
text(300, 646, "units · percentages · statewide counts", size=11.5, color=SOFT)
text(300, 662, "plus a model reviewer, advisory only", size=11.5, color=SOFT)

poly([(300, 668), (300, 704)], FAINT)

box(150, 706, 300, 44, CODE)
text(300, 729, "Anything unsupported?", size=14, bold=True)

poly([(450, 728), (556, 728)], EXIT)
text(460, 720, "yes", size=11, color=SOFT, italic=True, anchor="lm")
box(560, 706, 270, 44, EXIT)
text(695, 729, "Rewrite — once", size=14, bold=True)

poly([(830, 706), (830, 631), (464, 631)], EXIT)
text(596, 623, "re-checked, never trusted", size=11, color=SOFT, italic=True, anchor="lm")

poly([(695, 750), (695, 798)], EXIT)
text(701, 776, "still failing", size=11, color=SOFT, italic=True, anchor="lm")

box(560, 800, 270, 72, EXIT)
text(695, 820, "The data itself", size=14, bold=True)
text(695, 838, "figures and passages, shown raw", size=11.5, color=SOFT)
text(695, 854, "and marked unverified", size=11.5, color=SOFT)

poly([(300, 750), (300, 798)], FAINT)
text(306, 776, "no", size=11, color=SOFT, italic=True, anchor="lm")

box(150, 800, 300, 52, CODE)
text(300, 818, "Assembly", size=14, bold=True)
text(300, 836, "citations, chart and map — built from the data", size=11.5, color=SOFT)

poly([(300, 852), (300, 898)], FAINT)

box(150, 900, 300, 52, OK, alpha=0.15, width=1.8)
text(300, 918, "Answer", size=14, bold=True)
text(300, 936, "every figure traced to a source", size=11.5, color=SOFT)

# legend
for i, (label, col, a) in enumerate([
        ("calls a language model", LLM, 0.20),
        ("plain code — no model", CODE, 0.13),
        ("stops early", EXIT, 0.13)]):
    x = 150 + i * 210
    d.rounded_rectangle([x * S, 972 * S, (x + 16) * S, 984 * S], radius=2 * S,
                        fill=blend(col, GROUND, a), outline=col,
                        width=max(int(1.5 * S), 2))
    text(x + 22, 978, label, size=11.5, color=SOFT, anchor="lm")

img.save(OUT)
print(f"wrote {OUT}  ({W}x{H})")
