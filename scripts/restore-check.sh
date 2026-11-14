#!/usr/bin/env bash
# Verify a backup archive against its checksum and list its contents. Usage: scripts/restore-check.sh backups/<file>.tar.gz
set -euo pipefail
( cd "$(dirname "$1")" && sha256sum -c "$(basename "$1").sha256" )
tar -tzf "$1" | head -20
