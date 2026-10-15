#!/bin/sh
# Assemble the public website from tracked files only, into site/ (gitignored),
# then deploy it from inside site/: `vercel deploy` for a preview, `vercel
# deploy --prod` once analysis/site_check.py passes. The site is web/ as it is
# (no build step) plus the poster PDF. Nothing from the local working documents
# in docs/ is copied, and site/.vercel (the project link) is kept.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE="$ROOT/site"
mkdir -p "$SITE"
find "$SITE" -mindepth 1 -maxdepth 1 ! -name .vercel ! -name .vercelignore -exec rm -rf {} +
cp -R "$ROOT/web/." "$SITE/"
cp "$ROOT/docs/booth/poster.pdf" "$SITE/booth/poster.pdf"
printf '.env*\n.gitignore\n' > "$SITE/.vercelignore"
if find "$SITE" -name '.env*' -not -path '*/.vercel/*' | grep -q .; then
  echo "REFUSING: an .env file is in site/"; exit 1
fi
echo "staged: $(cd "$SITE" && find . -type f -not -path './.vercel/*' | wc -l | tr -d ' ') files, $(du -sh "$SITE" | cut -f1)"
