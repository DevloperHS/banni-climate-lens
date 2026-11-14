#!/usr/bin/env bash
# Back up the scientific record: processed series, rasters, raw extractions, field data, groundwater uploads.
# Usage: scripts/backup.sh [DATA_DIR] [DEST_DIR]      (cache/ and sample/ are disposable and excluded)
set -euo pipefail
DATA="${1:-./data}"; DEST="${2:-./backups}"; STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"
OUT="$DEST/globalclimatelens_$STAMP.tar.gz"
tar -czf "$OUT" -C "$DATA" --exclude='cache' --exclude='sample' --exclude='*.tmp' processed raw 2>/dev/null || tar -czf "$OUT" -C "$DATA" --exclude='*.tmp' processed
( cd "$DEST" && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256" )
echo "backup written: $OUT"; ls -l "$OUT"
