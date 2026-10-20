"""Build the offline booth copy: each screen as one standalone HTML file.

Every stylesheet and script is written into the page, so a laptop needs only a
browser, no network and no folder structure. Run analysis/stage_site.sh first,
since this reads the staged site/ folder.

    /usr/bin/python3 analysis/make_offline.py ~/Desktop/"CV2X-IDS booth offline"
"""
import re, shutil, sys
from pathlib import Path
SITE = Path.home() / "Documents/capstone-cv2x-ids/site"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
WALK, LIVE = "1 Walkthrough slides.html", "2 Live highway monitor.html"

def inline(page):
    base = page.parent; t = page.read_text()
    t = re.sub(r'<link rel="stylesheet" href="([^"]+)">',
               lambda m: "<style>\n" + (base / m[1]).read_text() + "\n</style>", t)
    t = re.sub(r'<script src="([^"]+)"></script>',
               lambda m: "<script>\n" + (base / m[1]).read_text() + "\n</script>", t)
    assert 'src="' not in re.sub(r'<script>.*?</script>', '', t, flags=re.S), page
    return t

w = inline(SITE / "index.html")
for a, b in (('href="live/index.html"', f'href="{LIVE}"'), ('href="booth/poster.pdf"', 'href="poster.pdf"')):
    assert w.count(a) == 1, a; w = w.replace(a, b)
(OUT / WALK).write_text(w)
(OUT / LIVE).write_text(inline(SITE / "live/index.html"))
shutil.copy(SITE / "booth/poster.pdf", OUT / "poster.pdf")
print("\n".join(f"{p.name}  {p.stat().st_size/1e6:.1f} MB" for p in sorted(OUT.iterdir())))
