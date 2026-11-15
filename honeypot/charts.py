#!/usr/bin/env python3
"""Charts for Admin > Model accuracy (standard library only).

A chart is described once, as shapes and text on a Canvas, and written out two ways: as SVG for
the web page and as PDF drawing commands for the download. That keeps the page and the PDF the
same picture.

  page_charts(report)  ->  {"bars": <svg>, "lines": <svg>}
  chart_notes(report)  ->  short sentences shown under the line chart
  build_pdf(report)    ->  bytes of a one-page PDF (US Letter)

`report` is what accuracy.report() returns.
"""
import html, json, time

# One color per model, the same in both charts; text always uses the ink colors.
# "Both together" is drawn dashed with ring markers, so it stays readable where it has the same
# value as one of the two models and their lines run on top of each other.
SERIES = [("content", "Content model", "#2a78d6", "solid"),
          ("behavior", "Behavior model", "#eb6834", "solid"),
          ("combined", "Both together", "#1baf7a", "dash")]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
CATEGORY_NAMES = {"Allow": "Allow", "Shadow AI": "Shadow AI", "Automated AI Pipelines": "Automated"}
MAX_POINTS = 12             # the original models plus the most recent updates
DASH = (6.0, 4.0)
FONT = "Helvetica, Arial, sans-serif"      # the layout below is measured with Helvetica's widths

# character widths (1/1000 of the font size) of Helvetica and Helvetica-Bold, characters 32..126
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556,
      556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667,
      556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556,
      556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722,
      500, 500, 500, 334, 260, 334, 584]
_WB = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556,
       556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722,
       611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556,
       611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778,
       556, 556, 500, 389, 280, 389, 584]


def text_width(s, size, bold=False):
    table = _WB if bold else _W
    return sum(table[ord(ch) - 32] if 32 <= ord(ch) <= 126 else 556 for ch in s) * size / 1000.0


def wrap(text, size, width, bold=False):
    """Break `text` into lines no wider than `width`."""
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if line and text_width(trial, size, bold) > width:
            lines.append(line); line = word
        else:
            line = trial
    return lines + ([line] if line else [])


def pct(v):
    return "n/a" if v is None else f"{round(v * 100)}%"


def _n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return " ".join(_n(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def _circle_path(cx, cy, r):
    k = r * 0.5523
    return [("M", cx + r, cy), ("C", cx + r, cy + k, cx + k, cy + r, cx, cy + r),
            ("C", cx - k, cy + r, cx - r, cy + k, cx - r, cy), ("C", cx - r, cy - k, cx - k, cy - r, cx, cy - r),
            ("C", cx + k, cy - r, cx + r, cy - k, cx + r, cy), ("Z",)]


def _spoken(tip):
    """The figures of a bar or of a version as one sentence, for screen readers."""
    head = tip.get("head", "") + (", " + tip["sub"] if tip.get("sub") else "")
    return head + ": " + ", ".join(f"{r[0]} {r[1]}" for r in (tip.get("rows") or []) + (tip.get("more") or []))


class Canvas:
    """Shapes and text with the origin at the top left, in points (1 point = 1 SVG unit)."""

    def __init__(self, width, height):
        self.w, self.h, self.ops = width, height, []

    # ---- drawing
    def path(self, cmds, fill=None, stroke=None, sw=1.0, dash=None, hover=None):
        """hover: a key. The shape is then drawn on the web page only, hidden until the group with
        the same key is pointed at (the page's script shows it)."""
        self.ops.append(("path", cmds, fill, stroke, sw, dash, hover))

    def hbar(self, x, y, w, h, fill, r=4.0):
        """A bar that grows to the right: square at the baseline, rounded at the data end."""
        r = max(0.0, min(r, w, h / 2.0)); k = r * 0.5523
        self.path([("M", x, y), ("L", x + w - r, y), ("C", x + w - r + k, y, x + w, y + r - k, x + w, y + r),
                   ("L", x + w, y + h - r), ("C", x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h),
                   ("L", x, y + h), ("Z",)], fill=fill)

    def circle(self, cx, cy, r, fill):
        self.path(_circle_path(cx, cy, r), fill=fill)

    def ring(self, cx, cy, r, stroke, sw=2.0):
        self.path(_circle_path(cx, cy, r), stroke=stroke, sw=sw)

    def line(self, x1, y1, x2, y2, stroke, sw=1.0, dash=None, hover=None):
        self.path([("M", x1, y1), ("L", x2, y2)], stroke=stroke, sw=sw, dash=dash, hover=hover)

    def polyline(self, pts, stroke, sw=2.0, dash=None):
        if len(pts) > 1:
            self.path([("M",) + tuple(pts[0])] + [("L",) + tuple(p) for p in pts[1:]], stroke=stroke, sw=sw, dash=dash)

    def text(self, x, y, s, size=10.0, anchor="start", bold=False, color=INK):
        """One line of text; y is the baseline. anchor: start, middle or end."""
        self.ops.append(("text", x, y, [(str(s), bold, color)], size, anchor))

    def text_parts(self, x, y, parts, size=10.0):
        """A line made of pieces with their own weight and color: [(text, bold, color), ...]."""
        self.ops.append(("text", x, y, [(str(s), b, c) for s, b, c in parts], size, "start"))

    # ---- web page only: a group that reacts to the pointer, and its invisible hit area
    def open_group(self, css_class, tip, key=None):
        self.ops.append(("open", css_class, tip, key))

    def close_group(self):
        self.ops.append(("close",))

    def hit(self, x, y, w, h):
        self.ops.append(("hit", x, y, w, h))

    # ---- output
    def to_svg(self, label):
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(self.w)} {_n(self.h)}" role="group" '
               f'aria-label="{html.escape(label, quote=True)}" class="pg-chart" font-family="{FONT}">']
        for op in self.ops:
            kind = op[0]
            if kind == "path":
                _, cmds, fill, stroke, sw, dash, hover = op
                d = " ".join(c[0] + " ".join(_n(v) for v in c[1:]) for c in cmds)
                attrs = f'fill="{fill or "none"}"'
                if stroke:
                    attrs += f' stroke="{stroke}" stroke-width="{_n(sw)}" stroke-linejoin="round"'
                    attrs += (f' stroke-dasharray="{_n(dash[0])} {_n(dash[1])}"' if dash else ' stroke-linecap="round"')
                if hover is not None:
                    attrs += f' class="pg-hover" data-key="{html.escape(str(hover), quote=True)}" opacity="0"'
                out.append(f'<path d="{d}" {attrs}/>')
            elif kind == "text":
                _, x, y, parts, size, anchor = op
                spans = "".join(f'<tspan fill="{c}"' + (' font-weight="700"' if b else "") + f'>{html.escape(s)}</tspan>'
                                for s, b, c in parts)
                out.append(f'<text x="{_n(x)}" y="{_n(y)}" font-size="{_n(size)}" text-anchor="{anchor}" '
                           f'xml:space="preserve">{spans}</text>')
            elif kind == "open":
                key = "" if op[3] is None else f' data-key="{html.escape(str(op[3]), quote=True)}"'
                out.append(f'<g class="{op[1]}" tabindex="0" role="img" aria-label="{html.escape(_spoken(op[2]), quote=True)}"{key} '
                           f'data-tip="{html.escape(json.dumps(op[2]), quote=True)}">')
            elif kind == "close":
                out.append("</g>")
            elif kind == "hit":
                _, x, y, w, h = op
                out.append(f'<rect class="pg-hit" x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" '
                           'fill="none" pointer-events="all"/>')
        return "".join(out) + "</svg>"

    def to_pdf_ops(self):
        """PDF drawing commands for a page as tall as this canvas."""
        H = self.h
        out = ["1 J 1 j"]
        for op in self.ops:
            if op[0] == "path":
                _, cmds, fill, stroke, sw, dash, hover = op
                if hover is not None:
                    continue
                seg = []
                if fill:
                    seg.append(_rgb(fill) + " rg")
                if stroke:
                    seg.append(_rgb(stroke) + " RG " + _n(sw) + " w")
                if dash:
                    seg.append(f"0 J [{_n(dash[0])} {_n(dash[1])}] 0 d")
                for c in cmds:
                    if c[0] == "M": seg.append(f"{_n(c[1])} {_n(H - c[2])} m")
                    elif c[0] == "L": seg.append(f"{_n(c[1])} {_n(H - c[2])} l")
                    elif c[0] == "C": seg.append(f"{_n(c[1])} {_n(H - c[2])} {_n(c[3])} {_n(H - c[4])} {_n(c[5])} {_n(H - c[6])} c")
                    else: seg.append("h")
                seg.append("B" if fill and stroke else "f" if fill else "S")
                if dash:
                    seg.append("[] 0 d 1 J")
                out.append(" ".join(seg))
            elif op[0] == "text":
                _, x, y, parts, size, anchor = op
                total = sum(text_width(s, size, b) for s, b, _ in parts)
                x0 = x - total if anchor == "end" else x - total / 2.0 if anchor == "middle" else x
                for s, b, c in parts:
                    esc = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                    out.append(f"BT {_rgb(c)} rg /{'F2' if b else 'F1'} {_n(size)} Tf {_n(x0)} {_n(H - y)} Td ({esc}) Tj ET")
                    x0 += text_width(s, size, b)
        return "\n".join(out)


# ------------------------------------------------------------------ what a figure breaks down into
def breakdown(pt, key):
    """The parts behind one figure of a version, as [label, value] pairs."""
    if key == "content":
        return [[CATEGORY_NAMES.get(c, c) + " prompts", pct(v)] for c, v in (pt.get("content_by_category") or {}).items()]
    if key == "behavior":
        out = []
        if pt.get("people_kept") is not None:
            out.append(["People recognized as people", pct(pt["people_kept"])])
        if pt.get("agents_caught") is not None:
            out.append(["Agents caught", pct(pt["agents_caught"])])
        return out
    return []


MEANING = {"content": "The category from the text of the prompt alone",
           "behavior": "Person or agent, from typing and mouse behavior",
           "combined": "The final category: Allow, Shadow AI or Automated AI Pipeline"}


def detail_rows(pt):
    """The three figures of a version with what each measures and its breakdown, for the table
    under the bar chart."""
    return [{"name": name, "value": pct(pt.get(key)), "measures": MEANING[key], "parts": breakdown(pt, key)}
            for key, name, _, _ in SERIES]


def detail_sentence(pt):
    """The same breakdown as one or two sentences (used in the PDF)."""
    parts = []
    by = pt.get("content_by_category") or {}
    if by:
        parts.append("Content model by category: " + ", ".join(f"{CATEGORY_NAMES.get(c, c)} {pct(v)}" for c, v in by.items()) + ".")
    if pt.get("people_kept") is not None or pt.get("agents_caught") is not None:
        parts.append(f"Behavior model: people recognized as people {pct(pt.get('people_kept'))}, "
                     f"agents caught {pct(pt.get('agents_caught'))}.")
    return " ".join(parts)


# ------------------------------------------------------------------ the two charts
def draw_bars(cv, x, y, w, current):
    """Bar chart of the three figures for the models in use. Returns the height it used."""
    label_w, value_w, row_h, bar_h = 104.0, 52.0, 32.0, 20.0
    px, pw, top = x + label_w, w - label_w - value_w, y + 4.0
    bottom = top + row_h * len(SERIES)
    for t in (0, 25, 50, 75, 100):
        gx = px + pw * t / 100.0
        cv.line(gx, top, gx, bottom, AXIS if t == 0 else GRID, 1.0)
        cv.text(gx, bottom + 13, f"{t}%", 9, "middle", color=MUTED)
    for i, (key, name, color, _) in enumerate(SERIES):
        cy = top + i * row_h + row_h / 2.0
        v = current.get(key)
        cv.text(px - 10, cy + 3.6, name, 10.5, "end", color=INK)
        if v is None:
            cv.text(px + 8, cy + 3.6, "not measured yet", 10, color=MUTED)
            continue
        cv.open_group("pg-bar", {"head": name, "rows": [["Accuracy", pct(v), color]], "more": breakdown(current, key)})
        cv.hbar(px, cy - bar_h / 2.0, pw * v, bar_h, color)
        cv.text(px + pw * v + 6, cy + 3.6, pct(v), 10.5, bold=True, color=INK)
        cv.hit(px, cy - row_h / 2.0, pw + value_w, row_h)
        cv.close_group()
    return (bottom + 20) - y


def shown_points(history):
    """The original models and the most recent updates, at most MAX_POINTS."""
    return history if len(history) <= MAX_POINTS else [history[0]] + history[-(MAX_POINTS - 1):]


def _marker(cv, cx, cy, color, style, r=4.0):
    if style == "dash":
        cv.ring(cx, cy, r + 0.5, color, 2.0 if r >= 4 else 1.6)
    else:
        cv.circle(cx, cy, r, color)


def _axis_labels(cv, xs, labels, y, size=9.0, gap=8.0):
    """Labels under the axis. The first and the last are always written; the ones between are
    written where they do not run into a neighbor."""
    n = len(xs)
    half = [text_width(s, size) / 2.0 for s in labels]
    keep = {0, n - 1}
    right_edge = xs[0] + half[0]
    for i in range(1, n - 1):
        if xs[i] - half[i] >= right_edge + gap and xs[i] + half[i] <= xs[n - 1] - half[n - 1] - gap:
            keep.add(i); right_edge = xs[i] + half[i]
    for i in sorted(keep):
        cv.text(xs[i], y, labels[i], size, "middle", color=MUTED)


def draw_lines(cv, x, y, w, h, history):
    """Line chart of the three figures across model versions, oldest on the left."""
    pts = shown_points(history)
    left, right, top, bottom = 38.0, 128.0, 28.0, 26.0
    px, py, pw, ph = x + left, y + top, w - left - right, h - top - bottom
    Y = lambda v: py + ph * (1.0 - v)
    # legend (always present with more than one series): a line key with its marker, and the name
    lx = px
    for key, name, color, style in SERIES:
        cv.line(lx, y + 10, lx + 26, y + 10, color, 2.0, DASH if style == "dash" else None)
        cv.circle(lx + 13, y + 10, 5.5, SURFACE); _marker(cv, lx + 13, y + 10, color, style, 3.2)
        cv.text(lx + 32, y + 13.5, name, 10, color=INK2)
        lx += 32 + text_width(name, 10) + 20
    for t in (0, 25, 50, 75, 100):
        gy = Y(t / 100.0)
        cv.line(px, gy, px + pw, gy, AXIS if t == 0 else GRID, 1.0)
        cv.text(px - 7, gy + 3.2, f"{t}%", 9, "end", color=MUTED)
    n = len(pts)
    pad = 16.0
    xs = [px + pw / 2.0] if n == 1 else [px + pad + (pw - 2 * pad) * i / (n - 1) for i in range(n)]
    _axis_labels(cv, xs, [p["x_label"] for p in pts], py + ph + 15)
    for i in range(n):                             # web page: the crosshair of each version, under the data
        cv.line(xs[i], py, xs[i], py + ph, MUTED, 1.0, hover=i)
    # lines first, then the markers: a white disc under each marker keeps it clear of the lines
    ends = []
    for key, name, color, style in SERIES:
        run, last = [], None
        for i, p in enumerate(pts):
            v = p.get(key)
            if v is None:
                cv.polyline(run, color, 2.0, DASH if style == "dash" else None); run = []
            else:
                run.append((xs[i], Y(v))); last = (xs[i], Y(v), v)
        cv.polyline(run, color, 2.0, DASH if style == "dash" else None)
        if last:
            ends.append([last[1], last[0], last[1], name, last[2], color, style])   # label y, then the point
    for key, name, color, style in SERIES:
        for i, p in enumerate(pts):
            if p.get(key) is not None:
                cv.circle(xs[i], Y(p[key]), 6.5, SURFACE)
    for key, name, color, style in SERIES:
        for i, p in enumerate(pts):
            if p.get(key) is not None:
                _marker(cv, xs[i], Y(p[key]), color, style)
    # direct labels in the right margin; where two would touch they are spread out, with a leader line
    ends.sort(key=lambda e: e[0])
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 13.0)
    if ends and ends[-1][0] > py + ph:
        ends[-1][0] = py + ph
        for i in range(len(ends) - 2, -1, -1):
            ends[i][0] = min(ends[i][0], ends[i + 1][0] - 13.0)
    label_x = px + pw + 12
    for ly, ex, ey, name, v, color, style in ends:
        if abs(ly - ey) > 0.5 or ex < xs[-1] - 0.5:
            cv.line(ex + 7, ey, label_x - 5, ly, AXIS, 1.0)
        _marker(cv, label_x, ly, color, style, 3.0)
        cv.text_parts(label_x + 8, ly + 3.4, [(name + " ", False, INK2), (pct(v), True, INK)], 9.5)
    # web page: one band per version; pointing at it shows a crosshair and all three figures
    band = (xs[1] - xs[0]) if n > 1 else pw
    for i, p in enumerate(pts):
        x0, x1 = max(px, xs[i] - band / 2.0), min(px + pw, xs[i] + band / 2.0)
        cv.open_group("pg-band", {"head": p["name"] + (" (in use)" if p.get("in_use") else ""),
                                  "sub": p.get("made_text") or "before any update",
                                  "rows": [[name, pct(p.get(key)), color] for key, name, color, _ in SERIES],
                                  "more": [["Entries", str(p["entries"])]] if p.get("entries") is not None else []}, key=i)
        cv.hit(x0, py, x1 - x0, ph)
        cv.close_group()


def _same_everywhere(pts, a, b, tolerance=0.02):
    both = [(p[a], p[b]) for p in pts if p.get(a) is not None and p.get(b) is not None]
    return bool(both) and all(abs(u - v) <= tolerance for u, v in both)


def chart_notes(report, where="The chart shows"):
    """Short sentences under the line chart: what a reader could otherwise misread."""
    history = report["history"]; shown = shown_points(history)
    notes = []
    if len(history) == 1:
        notes.append("No model update has been made yet. Each update adds a point to this chart.")
    if len(shown) < len(history):
        notes.append(f"{where} the original models and the {len(shown) - 1} most recent of {len(history) - 1} updates.")
    names = {key: name for key, name, _, _ in SERIES}
    for a, b in (("behavior", "combined"), ("content", "combined"), ("content", "behavior")):
        if len(shown) > 1 and _same_everywhere(shown, a, b):
            notes.append(f"The {names[a]} and {names[b]} lines run on top of each other because their values are "
                         "nearly the same.")
    return notes


def page_charts(report):
    """The two charts as SVG, for the web page."""
    cur = report["current"]
    bars = Canvas(640, 10)
    bars.h = draw_bars(bars, 0, 0, 640, cur)
    lines = Canvas(640, 270)
    draw_lines(lines, 0, 0, 640, 270, report["history"])
    said = ", ".join(f"{name} {pct(cur.get(key))}" for key, name, _, _ in SERIES)
    return {"bars": bars.to_svg("Bar chart of the models in use: " + said + ". The same figures are in the table below."),
            "lines": lines.to_svg("Line chart of accuracy across model versions. The same figures are in the table below.")}


# ------------------------------------------------------------------ the PDF
HOW_TO_READ = ("Content model: the share of entries given the right category from their text alone. Behavior model: the "
               "share of entries where a person and an agent were told apart correctly. Both together: the share of "
               "entries given the right final category (Allow, Shadow AI or Automated AI Pipeline). The original models "
               "are measured on the collected study entries, which they were never trained on. Each update is estimated "
               "on participants and prompts that were held out of its training.")


def in_use_text(cur):
    return "the original models" if cur.get("kind") == "original" else "the update made " + (cur.get("made_text") or cur.get("version_id", ""))


def build_pdf(report):
    """A one-page PDF (US Letter) with both charts, the table of versions and how to read them."""
    W, H, M = 612.0, 792.0, 54.0
    inner, floor = W - 2 * M, H - 62.0            # nothing but the footer goes below `floor`
    cur, history = report["current"], report["history"]
    basis = wrap((cur.get("basis_text") or "") + " " + detail_sentence(cur), 9, inner)
    notes = [ln for note in chart_notes(report, "The chart and the table show") for ln in wrap(note, 8.5, inner)]
    how = wrap(HOW_TO_READ, 8.5, inner)
    rows = shown_points(history)

    # the line chart takes the room that is left; with very little room the oldest updates leave the table
    def chart_room(n_rows):
        used = (254 + 12.5 * len(basis) + 22 + (6 + 11.5 * len(notes) if notes else 0) + 21 + 13 * n_rows
                + 37 + 11.5 * (len(how) - 1))
        return floor - used
    while chart_room(len(rows)) < 120 and len(rows) > 2:
        rows = [rows[0]] + rows[2:]
    chart_h = max(100.0, min(200.0, chart_room(len(rows))))

    cv = Canvas(W, H)
    y = 66.0
    cv.text(M, y, "PromptGate AI: model accuracy", 17, bold=True)
    y += 17
    cv.text(M, y, f"Generated {report['generated_text']}   |   Models in use: {in_use_text(cur)}", 9.5, color=INK2)
    y += 9
    cv.line(M, y, W - M, y, AXIS, 1.0)

    y += 24
    cv.text(M, y, "Accuracy of the models in use", 12, bold=True)
    y += 6
    y += draw_bars(cv, M, y, inner, cur)
    y += 12
    for ln in basis:
        cv.text(M, y, ln, 9, color=INK2); y += 12.5

    y += 16
    cv.text(M, y, "Accuracy over time", 12, bold=True)
    y += 6
    draw_lines(cv, M, y, inner, chart_h, history)
    y += chart_h
    if notes:
        y += 4
        for ln in notes:
            y += 11.5; cv.text(M, y, ln, 8.5, color=MUTED)

    # table of versions
    y += 18 if notes else 16
    col_made, r_content, r_behavior, r_both, r_entries = M + 150, M + 322, M + 388, M + 458, W - M
    cv.text(M, y, "Version", 8.5, bold=True, color=INK2); cv.text(col_made, y, "Made", 8.5, bold=True, color=INK2)
    for rx, label in ((r_content, "Content"), (r_behavior, "Behavior"), (r_both, "Both together"), (r_entries, "Entries")):
        cv.text(rx, y, label, 8.5, "end", bold=True, color=INK2)
    y += 5
    cv.line(M, y, W - M, y, AXIS, 1.0)
    for p in rows:
        y += 13
        cv.text_parts(M, y, [(p["name"], False, INK)] + ([("  in use", True, INK)] if p.get("in_use") else []), 9)
        cv.text(col_made, y, p.get("made_text") or "before any update", 9, color=INK2)
        for rx, key in ((r_content, "content"), (r_behavior, "behavior"), (r_both, "combined")):
            cv.text(rx, y, pct(p.get(key)), 9, "end")
        cv.text(r_entries, y, "" if p.get("entries") is None else str(p["entries"]), 9, "end", color=INK2)
        cv.line(M, y + 4, W - M, y + 4, GRID, 0.6)

    y += 24
    cv.text(M, y, "How to read this", 9.5, bold=True, color=INK2)
    y += 13
    for ln in how:
        cv.text(M, y, ln, 8.5, color=INK2); y += 11.5
    cv.text(M, H - 36, "PromptGate AI  -  University of North Dakota research study", 8, color=MUTED)
    return _pdf_bytes(cv.to_pdf_ops(), "PromptGate AI: model accuracy", W, H)


def _pdf_bytes(content, title, W, H):
    stream = content.encode("cp1252", "replace")
    stamp = time.strftime("D:%Y%m%d%H%M%SZ", time.gmtime())
    esc = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> "
             "/Contents 4 0 R >>" % (_n(W), _n(H))).encode("ascii"),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            ("<< /Title (%s) /Producer (PromptGate AI) /CreationDate (%s) >>" % (esc, stamp)).encode("cp1252", "replace")]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)
