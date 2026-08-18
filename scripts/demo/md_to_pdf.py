#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Render one of the film sheets to a phone-readable A5 PDF, via headless Chrome.

    .venv/Scripts/python.exe scripts/demo/md_to_pdf.py docs/demo/film/RECORD-THE-SCREEN.md out.pdf

WHY THIS EXISTS. The founder follows the shooting sheet on a phone while both hands are on the
keyboard, and the sheet changed six times during one shoot. Regenerating it by hand each time is
how a stale copy ends up being the one in front of the camera.

TWO THINGS THIS DOES THAT A GENERIC CONVERTER DOES NOT.

*One: a leading space inside a fenced block is made visible.* ``\u0020verified at zero`` is typed on
camera and its leading space is load-bearing -- it joins a pre-typed head. A space is invisible on
paper and several copy-paste paths trim it, so it is rendered as a red dot the eye cannot miss.

*Two: A5 pages, not A4.* A4 scaled to a phone puts the type below reading size at arm's length.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

CSS = """@page{size:A5 portrait;margin:10mm 8mm}*{box-sizing:border-box}
body{font:10.5pt/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#111;margin:0}
h1{font-size:19pt;border-bottom:3px solid #111;padding-bottom:5px;margin:0 0 10px;page-break-after:avoid}
h1:not(:first-of-type){page-break-before:always}
h2{font-size:14pt;margin:16px 0 6px;page-break-after:avoid;border-left:5px solid #111;padding-left:8px}
h3{font-size:11.5pt;margin:12px 0 4px;page-break-after:avoid}
p{margin:6px 0}ul,ol{margin:6px 0 6px 18px;padding:0}li{margin:3px 0}
code{font-family:Consolas,monospace;font-size:.88em;background:#eee;padding:1px 4px;border-radius:3px;word-break:break-all}
pre.type{background:#111;color:#fff;padding:10px 12px;border-radius:5px;font-family:Consolas,monospace;
 font-size:11pt;white-space:pre-wrap;word-break:break-all;margin:8px 0;page-break-inside:avoid}
.sp{background:#c62828;color:#fff;padding:0 3px;border-radius:2px;margin-right:1px}
blockquote{border-left:4px solid #c62828;background:#fdf3f3;margin:8px 0;padding:7px 11px;page-break-inside:avoid}
blockquote p{margin:4px 0}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:9pt}
th{background:#111;color:#fff;text-align:left;padding:5px 6px}
td{border-bottom:1px solid #ccc;padding:5px 6px;vertical-align:top}
tr{page-break-inside:avoid}hr{border:0;border-top:1px solid #bbb;margin:14px 0}"""


def _inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)


def render(md: str) -> str:
    md = re.sub(r"^<!--.*?-->\s*", "", md, flags=re.S)
    out: list[str] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            body = html.escape("\n".join(buf))
            body = re.sub(r"^ ", r'<span class="sp">&middot;</span>', body, flags=re.M)
            out.append(f'<pre class="type">{body}</pre>')
            continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            hdr = [c.strip() for c in ln.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            tb = "<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in hdr) + "</tr></thead><tbody>"
            for r in rows:
                tb += "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
            out.append(tb + "</tbody></table>")
            continue
        m = re.match(r"^(#{1,3}) (.+)$", ln)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if ln.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            sub = []
            for para in re.split(r"\n\s*\n", "\n".join(buf)):
                if re.match(r"^\* ", para.strip()):
                    items = [re.sub(r"^\* ", "", x) for x in para.strip().split("\n* ")]
                    sub.append("<ul>" + "".join(f"<li>{_inline(x.replace(chr(10), ' '))}</li>" for x in items) + "</ul>")
                elif para.strip():
                    sub.append(f"<p>{_inline(para.replace(chr(10), ' '))}</p>")
            out.append("<blockquote>" + "".join(sub) + "</blockquote>")
            continue
        if re.match(r"^[-*] |\d+\. ", ln):
            tag = "ol" if re.match(r"^\d", ln) else "ul"
            items: list[str] = []
            while i < len(lines) and re.match(r"^([-*] |\d+\. |\s{2,}\S)", lines[i]):
                if re.match(r"^([-*] |\d+\. )", lines[i]):
                    items.append(re.sub(r"^([-*] |\d+\. )", "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if ln.strip() == "---":
            out.append("<hr>")
            i += 1
            continue
        if not ln.strip():
            i += 1
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,3} |[-*] |\d+\. |\||>|```|---)", lines[i]):
            buf.append(lines[i])
            i += 1
        out.append(f"<p>{_inline(' '.join(buf))}</p>")
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Shooting sheet</title>'
        f"<style>{CSS}</style></head><body>{chr(10).join(out)}</body></html>"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, dest = Path(argv[1]), Path(argv[2])
    browser = next((b for b in CHROME if os.path.exists(b)), None)
    if browser is None:
        print("no Chrome or Edge found; cannot render", file=sys.stderr)
        return 1
    tmp = Path(tempfile.gettempdir()) / (src.stem + ".html")
    tmp.write_text(render(src.read_text(encoding="utf-8")), encoding="utf-8")
    subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={dest}", tmp.as_uri()],
        check=True, capture_output=True, timeout=180,
    )
    blob = dest.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", blob))
    print(f"{dest}  {len(blob):,} bytes  {pages} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
