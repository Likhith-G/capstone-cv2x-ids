#!/bin/bash
# Build the two distributable packages from the release bundle.
#
# Store mode (-0) throughout: the shards are already gzipped, so deflate spends
# minutes to save nothing. The small package carries one scenario plus every
# top level file, because the eight small files are what check_release.py reads
# to know what it is looking at, and a scenario without them verifies nothing.
#
#   ./analysis/make_package.sh [release_dir] [out_dir]
set -euo pipefail

SRC="${1:-$HOME/ns3-v2x/runs/release}"
OUT="${2:-$HOME/Downloads}"
VER="1.0.0"
REF="highway_sparse"

[ -d "$SRC/shards" ] || { echo "no shards/ under $SRC"; exit 1; }
mkdir -p "$OUT"
cd "$(dirname "$SRC")"
BASE="$(basename "$SRC")"

echo "full package, all scenarios"
rm -f "$OUT/cv2x-ids-$VER.zip"
zip -0 -r -q "$OUT/cv2x-ids-$VER.zip" "$BASE" -x '*.DS_Store'

echo "reference package, $REF only"
rm -f "$OUT/cv2x-ids-$VER-$REF.zip"
zip -0 -q "$OUT/cv2x-ids-$VER-$REF.zip" "$BASE"/*.* -x '*.DS_Store'
zip -0 -r -q "$OUT/cv2x-ids-$VER-$REF.zip" "$BASE/shards/$REF" -x '*.DS_Store'

cd "$OUT"
shasum -a 256 "cv2x-ids-$VER.zip" "cv2x-ids-$VER-$REF.zip" > "cv2x-ids-$VER-SHA256.txt"
ls -lh "cv2x-ids-$VER.zip" "cv2x-ids-$VER-$REF.zip"
cat "cv2x-ids-$VER-SHA256.txt"
