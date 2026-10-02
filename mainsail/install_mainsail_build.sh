#!/usr/bin/env bash
# Install (or undo) the Mainsail build that includes the Toolchanger panel.
#   ./install_mainsail_build.sh [path/to/mainsail.zip]   install (backs up ~/mainsail first)
#   ./install_mainsail_build.sh --restore                put the backed-up Mainsail back
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAINSAIL_DIR="${MAINSAIL_DIR:-$HOME/mainsail}"
BACKUP="${MAINSAIL_DIR}.official-backup"

if [[ "${1:-}" == "--restore" ]]; then
  [[ -d "$BACKUP" ]] || { echo "No backup at $BACKUP"; exit 1; }
  rm -rf "$MAINSAIL_DIR" && mv "$BACKUP" "$MAINSAIL_DIR"
  echo "Official Mainsail restored. Reload the browser page."
  exit 0
fi

ZIP="${1:-$(ls "$HERE"/mainsail-btc-toolchanger-*.zip 2>/dev/null | sort -V | tail -n1)}"
[[ -f "$ZIP" ]] || { echo "Mainsail zip not found (pass its path)"; exit 1; }
[[ -d "$MAINSAIL_DIR" ]] || { echo "Mainsail not found at $MAINSAIL_DIR (set MAINSAIL_DIR=...)"; exit 1; }
command -v unzip >/dev/null || { echo "Please install unzip: sudo apt install unzip"; exit 1; }

if [[ ! -d "$BACKUP" ]]; then
  cp -a "$MAINSAIL_DIR" "$BACKUP"
  echo "Backed up the official Mainsail to $BACKUP"
fi

# keep the user's config.json (printer list etc.)
TMP="$(mktemp -d)"
[[ -f "$MAINSAIL_DIR/config.json" ]] && cp "$MAINSAIL_DIR/config.json" "$TMP/config.json"
find "$MAINSAIL_DIR" -mindepth 1 -delete
unzip -q "$ZIP" -d "$MAINSAIL_DIR"
[[ -f "$TMP/config.json" ]] && cp "$TMP/config.json" "$MAINSAIL_DIR/config.json"
rm -rf "$TMP"

echo "Installed $(basename "$ZIP") into $MAINSAIL_DIR"
echo "Reload Mainsail in the browser (Ctrl+Shift+R). The Toolchanger panel appears on the dashboard"
echo "once the btc_dashboard add-on is loaded in Klipper."
echo
echo "NOTE: Mainsail updates from the Update Manager will replace this build with the official one."
echo "      Re-run this script afterwards, or point [update_manager mainsail] at your own fork (see README)."
