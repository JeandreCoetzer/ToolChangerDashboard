#!/usr/bin/env bash
# Install (or undo) the Mainsail / Fluidd build that includes the Toolchanger panel.
#   install_ui_build.sh mainsail|fluidd                  download (if needed) and install
#   install_ui_build.sh mainsail|fluidd path/to/x.zip    install a zip you already have
#   install_ui_build.sh mainsail|fluidd --restore        put the backed-up official build back
# The official build is copied to ~/<ui>.official-backup before the first install.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../ui-builds.conf
source "${REPO_DIR}/ui-builds.conf"

UI="${1:-}"
case "$UI" in
  mainsail) NAME="Mainsail"; ZIP_NAME="$MAINSAIL_ZIP"; SHA="$MAINSAIL_SHA256"; UI_DIR="${MAINSAIL_DIR:-$HOME/mainsail}" ;;
  fluidd)   NAME="Fluidd";   ZIP_NAME="$FLUIDD_ZIP";   SHA="$FLUIDD_SHA256";   UI_DIR="${FLUIDD_DIR:-$HOME/fluidd}" ;;
  *) echo "Usage: $0 mainsail|fluidd [zip|--restore]"; exit 1 ;;
esac
shift
BACKUP="${UI_DIR}.official-backup"
CACHE="${REPO_DIR}/${UI}/${ZIP_NAME}"

if [[ "${1:-}" == "--restore" ]]; then
  [[ -d "$BACKUP" ]] || { echo "No backup at $BACKUP - nothing to restore."; exit 1; }
  rm -rf "$UI_DIR" && mv "$BACKUP" "$UI_DIR"
  echo "Official $NAME restored to $UI_DIR. Reload the browser page."
  exit 0
fi

[[ -d "$UI_DIR" ]] || { echo "$NAME not found at $UI_DIR (set ${UI^^}_DIR=...)"; exit 1; }
command -v unzip >/dev/null || { echo "Please install unzip: sudo apt install unzip"; exit 1; }

ZIP="${1:-$CACHE}"
if [[ ! -f "$ZIP" ]]; then
  command -v curl >/dev/null || { echo "Please install curl: sudo apt install curl"; exit 1; }
  echo "Downloading ${ZIP_NAME} (${RELEASE_TAG})..."
  curl -fL --retry 2 -o "${CACHE}.part" "${RELEASE_URL}/${ZIP_NAME}" \
    || { rm -f "${CACHE}.part"; echo "Download failed: ${RELEASE_URL}/${ZIP_NAME}"; exit 1; }
  mv "${CACHE}.part" "$CACHE"
  ZIP="$CACHE"
fi
# only check the checksum of the published build, not of a zip passed in by hand
if [[ $# -eq 0 ]]; then
  echo "${SHA}  ${ZIP}" | sha256sum -c --quiet - \
    || { echo "Checksum mismatch for ${ZIP} - delete it and run again."; exit 1; }
fi

if [[ ! -d "$BACKUP" ]]; then
  cp -a "$UI_DIR" "$BACKUP"
  echo "Backed up the official $NAME to $BACKUP"
fi

# keep the user's config.json (printer list, endpoints, ...)
TMP="$(mktemp -d)"
if [[ -f "$UI_DIR/config.json" ]]; then cp "$UI_DIR/config.json" "$TMP/config.json"; fi
find "$UI_DIR" -mindepth 1 -delete
unzip -q "$ZIP" -d "$UI_DIR"
if [[ -f "$TMP/config.json" ]]; then cp "$TMP/config.json" "$UI_DIR/config.json"; fi
rm -rf "$TMP"

echo "Installed $(basename "$ZIP") into $UI_DIR"
echo "Reload $NAME in the browser (Ctrl+Shift+R). The Toolchanger panel appears once the"
echo "btc_dashboard add-on is loaded in Klipper."
echo "Note: updating $NAME from the Update Manager puts the official build back; run this again afterwards."
