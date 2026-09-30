#!/usr/bin/env bash
# Sync the live integration from the Home Assistant config directory into this repo.
# Source of truth while developing is /home/jan/homeassistant/custom_components/warp_charger.
set -euo pipefail
SRC="${1:-/home/jan/homeassistant/custom_components/warp_charger}"
DST="$(cd "$(dirname "$0")" && pwd)/custom_components/warp_charger"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$SRC/" "$DST/"
git -C "$(dirname "$DST")/.." status --short
