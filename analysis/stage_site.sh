#!/bin/sh
# Assemble the public website from tracked files only, into site/ (gitignored),
# then deploy it with `vercel --prod` from inside site/. Nothing from the local
# working documents in docs/ is copied.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITE="$ROOT/site"
mkdir -p "$SITE/booth"
cp "$ROOT/docs/index.html" "$SITE/index.html"
cp "$ROOT/docs/booth/index.html" "$ROOT/docs/booth/replay.html" "$ROOT/docs/booth/poster.pdf" "$SITE/booth/"
echo "staged: $(cd "$SITE" && find . -type f -not -path './.vercel/*' | sort | tr '\n' ' ')"
