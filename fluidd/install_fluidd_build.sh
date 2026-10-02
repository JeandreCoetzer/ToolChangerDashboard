#!/usr/bin/env bash
# Install (or undo) the Fluidd build that includes the Toolchanger card.
#   ./install_fluidd_build.sh [path/to/fluidd.zip]       install (backs up ~/fluidd first)
#   ./install_fluidd_build.sh --restore                  put the backed-up Fluidd back
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLUIDD_DIR="${FLUIDD_DIR:-$HOME/fluidd}"
BACKUP="${FLUIDD_DIR}.official-backup"

if [[ "${1:-}" == "--restore" ]]; then
  [[ -d "$BACKUP" ]] || { echo "No backup at $BACKUP"; exit 1; }
  rm -rf "$FLUIDD_DIR" && mv "$BACKUP" "$FLUIDD_DIR"
  echo "Official Fluidd restored. Reload the browser page."
  exit 0
fi

ZIP="${1:-$(ls "$HERE"/fluidd-btc-toolchanger-*.zip 2>/dev/null | sort -V | tail -n1)}"
[[ -f "$ZIP" ]] || { echo "Fluidd zip not found (pass its path)"; exit 1; }
[[ -d "$FLUIDD_DIR" ]] || { echo "Fluidd not found at $FLUIDD_DIR (set FLUIDD_DIR=...)"; exit 1; }
command -v unzip >/dev/null || { echo "Please install unzip: sudo apt install unzip"; exit 1; }

if [[ ! -d "$BACKUP" ]]; then
  cp -a "$FLUIDD_DIR" "$BACKUP"
  echo "Backed up the official Fluidd to $BACKUP"
fi

# keep the user's config.json (printer list etc.)
TMP="$(mktemp -d)"
[[ -f "$FLUIDD_DIR/config.json" ]] && cp "$FLUIDD_DIR/config.json" "$TMP/config.json"
find "$FLUIDD_DIR" -mindepth 1 -delete
unzip -q "$ZIP" -d "$FLUIDD_DIR"
[[ -f "$TMP/config.json" ]] && cp "$TMP/config.json" "$FLUIDD_DIR/config.json"
rm -rf "$TMP"

echo "Installed $(basename "$ZIP") into $FLUIDD_DIR"
echo "Reload Fluidd in the browser (Ctrl+Shift+R). The Toolchanger card appears on the dashboard"
echo "once the btc_dashboard add-on is loaded in Klipper."
echo
echo "NOTE: Fluidd updates from the Update Manager will replace this build with the official one."
echo "      Re-run this script afterwards, or point [update_manager fluidd] at your own fork (see README)."
