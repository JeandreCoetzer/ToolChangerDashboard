#!/usr/bin/env bash
# BTC Dashboard uninstaller - removes the add-on, nginx site and config hooks,
# and puts the official Mainsail / Fluidd back if the Toolchanger build was installed.
# btc_dashboard.cfg is renamed, not deleted. Backups of edited files are kept.
set -euo pipefail
KLIPPER_DIR="${HOME}/klipper"
PRINTER_DATA="${HOME}/printer_data"
while getopts "k:d:" o; do case "$o" in k) KLIPPER_DIR="$OPTARG" ;; d) PRINTER_DATA="$OPTARG" ;; *) ;; esac; done
CONFIG_DIR="${PRINTER_DATA}/config"
STAMP="$(date +%Y%m%d-%H%M%S)"

rm -f "${KLIPPER_DIR}/klippy/extras/btc_dashboard.py"
echo "Removed Klipper add-on link"

if [[ -f "${CONFIG_DIR}/printer.cfg" ]] && grep -qE '^\[include btc_dashboard\.cfg\]' "${CONFIG_DIR}/printer.cfg"; then
  cp "${CONFIG_DIR}/printer.cfg" "${CONFIG_DIR}/printer.cfg.btcdash-${STAMP}.bak"
  sed -i '/^\[include btc_dashboard\.cfg\]/d' "${CONFIG_DIR}/printer.cfg"
  echo "Removed include from printer.cfg"
fi
[[ -f "${CONFIG_DIR}/btc_dashboard.cfg" ]] && mv "${CONFIG_DIR}/btc_dashboard.cfg" "${CONFIG_DIR}/btc_dashboard.cfg.removed-${STAMP}" \
  && echo "Renamed btc_dashboard.cfg (if it held [save_variables] that other macros use, move that section back)"

MC="${CONFIG_DIR}/moonraker.conf"
if [[ -f "$MC" ]] && grep -q '^\[update_manager btc_dashboard\]' "$MC"; then
  cp "$MC" "${MC}.btcdash-${STAMP}.bak"
  python3 - "$MC" <<'EOF'
import re, sys
p = sys.argv[1]; s = open(p).read()
s = re.sub(r"\n*\[update_manager btc_dashboard\][^\[]*", "\n\n", s).rstrip() + "\n"
open(p, "w").write(s)
EOF
  echo "Removed update manager entry"
fi

if [[ -e /etc/nginx/sites-enabled/btc-dashboard || -e /etc/nginx/sites-available/btc-dashboard ]]; then
  sudo rm -f /etc/nginx/sites-enabled/btc-dashboard /etc/nginx/sites-available/btc-dashboard
  sudo nginx -t && sudo systemctl reload nginx
  echo "Removed nginx site"
fi
for UI in mainsail fluidd; do
  if [[ -d "${HOME}/${UI}.official-backup" ]]; then
    bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/install_ui_build.sh" "$UI" --restore
  fi
done

echo "Done. Restart Klipper (and Moonraker) to finish."
