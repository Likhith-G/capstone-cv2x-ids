#!/usr/bin/env python3
"""
site_check.py: checks on the booth website in web/ before it is deployed.

1. No em or en dash anywhere, and none of the banned phrasings (a "public"
   dataset, "converged", a floor other than the pinned one).
2. Every number typed into the pages is on a short allow list; every other
   number must come from web/data through a data-n attribute, and every data-n
   path must resolve in the generated data.
3. Nothing is loaded from the network at run time: no external script,
   stylesheet, font or fetch, so the booth works offline.
4. The printed QR target (booth/index.html) and the live dashboard exist, and
   every drive the dashboard loads is present.

    /usr/bin/python3 analysis/site_check.py      exit 0 when clean
"""
import json
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
problems = []


def text_files():
    return [p for p in WEB.rglob("*") if p.suffix in (".html", ".js", ".css")]


# 1. dashes and banned phrases (data files included: they carry log text)
BANNED = [(r"[–—]", "an em or en dash"), (r"public dataset", "'public dataset'"),
          (r"\bconverged\b", "'converged'"), (r"99 percent", "'99 percent'")]
for p in text_files():
    s = p.read_text()
    for pat, what in BANNED:
        if re.search(pat, s, re.I):
            problems.append(f"{p.relative_to(WEB)}: {what}")

# 2. typed numbers in page text
ALLOW = {"1", "2", "3", "4", "5", "1,000", "23", "14", "2006", "2019", "2025", "1609.2", "103", "097", "460",
         "5G", "0", "00", "02", "95"}
pages = [WEB / "index.html", WEB / "live" / "index.html"]
data = {}
for js in (WEB / "data").glob("*.js"):
    for key, blob in re.findall(r"window\.SITE\.(\w+)=(\{.*\});\s*$", js.read_text(), re.M):
        data[key] = json.loads(blob)
for page in pages:
    html = page.read_text()
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", body)
    for n in re.findall(r"(?<![\w.])\d[\d,.]*\d|(?<![\w.])\d(?![\w])", visible):
        if n not in ALLOW:
            problems.append(f"{page.relative_to(WEB)}: typed number {n} (take it from web/data)")
    for path in re.findall(r'data-n="([^"]+)"', html):
        node = data
        for k in path.split("."):
            node = node.get(k) if isinstance(node, dict) else None
        if node is None:
            problems.append(f"{page.relative_to(WEB)}: data-n {path} does not resolve")

# 3. offline: nothing fetched from the network
for p in text_files():
    s = p.read_text()
    for pat in (r'<script[^>]+src="https?:', r'<link[^>]+href="https?:', r"url\(\s*['\"]?https?:",
                r"\bfetch\(", r"@import", r"XMLHttpRequest", r'type="module"'):
        if re.search(pat, s):
            problems.append(f"{p.relative_to(WEB)}: loads from the network or as a module ({pat})")

# 4. paths the booth depends on
for need in ("index.html", "booth/index.html", "booth/replay.html", "live/index.html", "data/live_meta.js"):
    if not (WEB / need).exists():
        problems.append(f"missing {need}")
live = (WEB / "live" / "index.html").read_text() if (WEB / "live" / "index.html").exists() else ""
for src in re.findall(r'src="\.\./(data/[^"]+)"', live):
    if not (WEB / src).exists():
        problems.append(f"live/index.html loads {src}, which is missing")
if "available from the authors on request" not in (WEB / "index.html").read_text().lower():
    problems.append("index.html: the dataset access line is missing")

for p in problems:
    print("FAIL", p)
print(f"site_check: {len(problems)} problem(s)")
sys.exit(1 if problems else 0)
