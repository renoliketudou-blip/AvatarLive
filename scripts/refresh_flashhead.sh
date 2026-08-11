#!/bin/bash
# Refresh the vendored SoulX-FlashHead flash_head/ package from upstream.
#
# The vendored copy lives at:
#   src/handlers/avatar/flashhead/SoulX-FlashHead/flash_head
#
# Upstream: https://github.com/Soul-AILab/SoulX-FlashHead
# Vendored commit: c2b0b0f (flash_head files byte-identical to 9bc03de)
#
# Usage:
#   bash scripts/refresh_flashhead.sh          # fetch latest, show diff
#   bash scripts/refresh_flashhead.sh --apply  # fetch and overwrite vendored copy
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/src/handlers/avatar/flashhead/SoulX-FlashHead/flash_head"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Cloning upstream SoulX-FlashHead (shallow)..."
git clone --depth 1 https://github.com/Soul-AILab/SoulX-FlashHead.git "$TMP/SoulX-FlashHead" >/dev/null 2>&1

UPSTREAM_COMMIT="$(git -C "$TMP/SoulX-FlashHead" rev-parse HEAD)"
echo "Upstream HEAD: $UPSTREAM_COMMIT"

if [ "${1:-}" != "--apply" ]; then
    echo "Dry run: diff between vendored copy and upstream (excluding local patches):"
    diff -r --exclude='__pycache__' \
         "$DEST" "$TMP/SoulX-FlashHead/flash_head" > "$TMP/diff.txt" || true
    grep -v "configs/infer_params.yaml\|utils/cpu_face_handler.py" "$TMP/diff.txt" | head -40 || true
    echo
    echo "Re-run with --apply to overwrite the vendored copy."
    echo "NOTE: after --apply, re-apply the local patches:"
    echo "  1. flash_head/configs/infer_params.yaml : sample_shift 5 -> 8"
    echo "  2. flash_head/utils/cpu_face_handler.py : lazy mediapipe import"
    exit 0
fi

rm -rf "$DEST"
cp -a "$TMP/SoulX-FlashHead/flash_head" "$DEST"
rm -rf "$DEST"/__pycache__
find "$DEST" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

echo "Vendored flash_head updated from $UPSTREAM_COMMIT"
echo "IMPORTANT: re-apply the two local patches listed above, then update NOTICE."
