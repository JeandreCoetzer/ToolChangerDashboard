#!/usr/bin/env bash
# BTC Dashboard installer
#   ./install.sh            interactive setup
#   ./install.sh -y         accept defaults (auto-detect everything)
#   ./install.sh -h         help
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KLIPPER_DIR="${HOME}/klipper"
PRINTER_DATA="${HOME}/printer_data"
PORT=8137
MOONRAKER_PORT=7125
ASSUME_YES=0

usage() {
  cat <<EOF
Usage: $0 [options]
  -k DIR   Klipper source folder          (default: ~/klipper)
  -d DIR   printer_data folder            (default: ~/printer_data)
  -p PORT  port for the dashboard page    (default: 8137)
  -m PORT  Moonraker port                 (default: 7125)
  -y       non-interactive, use defaults
EOF
}
while getopts "k:d:p:m:yh" o; do
  case "$o" in
    k) KLIPPER_DIR="$OPTARG" ;; d) PRINTER_DATA="$OPTARG" ;;
    p) PORT="$OPTARG" ;; m) MOONRAKER_PORT="$OPTARG" ;;
    y) ASSUME_YES=1 ;; h|*) usage; exit 0 ;;
  esac
done

CONFIG_DIR="${PRINTER_DATA}/config"
PRINTER_CFG="${CONFIG_DIR}/printer.cfg"
MOONRAKER_CONF="${CONFIG_DIR}/moonraker.conf"
DASH_CFG="${CONFIG_DIR}/btc_dashboard.cfg"
STAMP="$(date +%Y%m%d-%H%M%S)"

c_ok=$'\e[32m'; c_warn=$'\e[33m'; c_err=$'\e[31m'; c_b=$'\e[1m'; c_0=$'\e[0m'
info() { echo "${c_ok}==>${c_0} $*"; }
warn() { echo "${c_warn}!!${c_0} $*"; }
die()  { echo "${c_err}ERROR:${c_0} $*" >&2; exit 1; }

ask() {  # ask "question" default -> echoes answer
  local q="$1" def="$2" a
  if [[ $ASSUME_YES -eq 1 ]]; then echo "$def"; return; fi
  read -r -p "${c_b}${q}${c_0} [${def}]: " a </dev/tty || true
  echo "${a:-$def}"
}
choose() {  # choose "question" default opt1 opt2 ...
  local q="$1" def="$2"; shift 2
  local a
  while true; do
    a="$(ask "$q ($(IFS=/; echo "$*"))" "$def")"
    for o in "$@"; do [[ "$a" == "$o" ]] && { echo "$a"; return; }; done
    echo "Please answer one of: $*" >&2
  done
}
yesno() { [[ "$(choose "$1" "$2" y n)" == "y" ]]; }
backup() { if [[ -f "$1" ]]; then cp "$1" "$1.btcdash-${STAMP}.bak"; fi; }

# ---------------------------------------------------------------- checks
[[ $EUID -eq 0 && -z "${BTCDASH_ALLOW_ROOT:-}" ]] && die "Run as your normal user (the one Klipper runs as), not root."
[[ -d "${KLIPPER_DIR}/klippy/extras" ]] || die "Klipper not found at ${KLIPPER_DIR} (use -k)."
[[ -f "$PRINTER_CFG" ]] || die "printer.cfg not found in ${CONFIG_DIR} (use -d)."

echo
echo "${c_b}BTC Dashboard installer${c_0}"
echo "Klipper: ${KLIPPER_DIR}   Config: ${CONFIG_DIR}"
echo

# ---------------------------------------------------------------- detect
count_tools() { grep -rhoE '^\[gcode_macro _VARIABLES_T[0-9]+\]' "$CONFIG_DIR" --include='*.cfg' 2>/dev/null | sort -u | wc -l; }
has_section() { grep -rqE "^\[$1\]" "$CONFIG_DIR" --include='*.cfg' 2>/dev/null; }
FOUND_TOOLS="$(count_tools)"
HAS_BTC=0; has_section "gcode_macro _BTC_VARIABLES" && HAS_BTC=1
HAS_DOCKSLIDE=0; has_section "gcode_macro DOCKSLIDE_HOME" && HAS_DOCKSLIDE=1
# Ask the running Klipper first (only sections it actually loaded count),
# fall back to grepping config files, ignoring SAVE_CONFIG backups (printer-*.cfg) and *.bak
HAS_SAVEVARS=0
LIVE="$(curl -s --max-time 3 "http://localhost:${MOONRAKER_PORT}/printer/objects/query?configfile=settings" 2>/dev/null || true)"
if [[ "$LIVE" == *'"settings"'* ]]; then
  [[ "$LIVE" == *'"save_variables"'* ]] && HAS_SAVEVARS=1
elif grep -rlE '^\[save_variables\]' "$CONFIG_DIR" --include='*.cfg' 2>/dev/null | grep -vE '/printer-[0-9_]+\.cfg$' | grep -q .; then
  HAS_SAVEVARS=1
fi
HAS_SPOOLMAN=0; [[ -f "$MOONRAKER_CONF" ]] && grep -qE '^\[spoolman\]' "$MOONRAKER_CONF" && HAS_SPOOLMAN=1

[[ $HAS_BTC -eq 1 ]] || warn "No [gcode_macro _BTC_VARIABLES] found - install the BTC macros first, the dashboard reads them."
info "Found ${FOUND_TOOLS} tool(s), dockslide: $([[ $HAS_DOCKSLIDE -eq 1 ]] && echo yes || echo no), save_variables: $([[ $HAS_SAVEVARS -eq 1 ]] && echo yes || echo no), Spoolman: $([[ $HAS_SPOOLMAN -eq 1 ]] && echo yes || echo no)"
echo

# ---------------------------------------------------------------- questions
TOOLS="$(ask "How many tools? ('auto' = every _VARIABLES_Tn found)" auto)"
[[ "$TOOLS" == "auto" || "$TOOLS" =~ ^[0-9]+$ ]] || die "tools must be 'auto' or a number"

DOCK_SENSE="$(choose "Dock sense switches fitted? none = carriage switch only (Lineux default)" none none per_tool)"
DOCK_BUTTON="dock_sense_t{n}"
if [[ "$DOCK_SENSE" == "per_tool" ]]; then
  DOCK_BUTTON="$(ask "gcode_button name for each dock ({n} = tool number)" "dock_sense_t{n}")"
fi
CARRIAGE="$(ask "gcode_button name of the carriage switch" carriage_sense)"
DOCKSLIDE="$(choose "Dockslide installed?" "$([[ $HAS_DOCKSLIDE -eq 1 ]] && echo auto || echo no)" auto yes no)"
SPOOLMAN="$(choose "Spoolman integration? auto = use it when Moonraker has Spoolman" auto auto yes no)"
SAVE_OFFSETS=auto
ADD_SAVEVARS=0
if yesno "Keep offsets edited in the dashboard after a restart?" y; then
  SAVE_OFFSETS=yes
  if [[ $HAS_SAVEVARS -eq 0 ]]; then
    info "That needs a [save_variables] section - I'll add one to btc_dashboard.cfg."
    ADD_SAVEVARS=1
  fi
else
  SAVE_OFFSETS=no
fi

# ---------------------------------------------------------------- klipper module
info "Linking Klipper add-on"
ln -sf "${REPO_DIR}/klippy/btc_dashboard.py" "${KLIPPER_DIR}/klippy/extras/btc_dashboard.py"
# keep Klipper's git status clean
EXCL="${KLIPPER_DIR}/.git/info/exclude"
if [[ -f "$EXCL" ]] && ! grep -q "klippy/extras/btc_dashboard.py" "$EXCL"; then
  echo "klippy/extras/btc_dashboard.py" >> "$EXCL"
fi

# ---------------------------------------------------------------- config file
OLD_SAVEVARS=""   # a [save_variables] section that lives in our own file must survive a rewrite
OLD_PRESETS=""    # so must the user's presets / presets_tN lines
if [[ -f "$DASH_CFG" ]]; then
  OLD_SAVEVARS="$(awk '/^\[save_variables\]/{f=1} /^\[/&&!/^\[save_variables\]/{f=0} f' "$DASH_CFG")"
  OLD_PRESETS="$(grep -E '^presets(_t[0-9]+)?[[:space:]]*[:=]' "$DASH_CFG" || true)"
  if yesno "btc_dashboard.cfg already exists. Rewrite it from your answers? (your presets and [save_variables] are kept, and a backup is made)" n; then
    backup "$DASH_CFG"
  else
    SKIP_CFG=1
  fi
fi
if [[ -n "$OLD_SAVEVARS" ]]; then ADD_SAVEVARS=0; fi
if [[ "${SKIP_CFG:-0}" -ne 1 ]]; then
  info "Writing ${DASH_CFG}"
  {
    echo "# BTC Dashboard - generated by install.sh on $(date)"
    echo "# Edit and restart Klipper. All options: ${REPO_DIR}/config/btc_dashboard.cfg.example"
    echo
    echo "[btc_dashboard]"
    echo "tools: ${TOOLS}"
    echo "carriage_sense: ${CARRIAGE}"
    echo "dock_sense: ${DOCK_SENSE}"
    [[ "$DOCK_SENSE" == "per_tool" ]] && echo "dock_sense_button: ${DOCK_BUTTON}"
    echo "dockslide: ${DOCKSLIDE}"
    echo "spoolman: ${SPOOLMAN}"
    echo "save_offsets: ${SAVE_OFFSETS}"
    echo "#extruder_names: extruder, extruder1, extruder2"
    echo "#hotend_fan_names: hotend_fan0, hotend_fan1, hotend_fan2"
    echo "# temperature preset buttons (label:°C). Add presets_t<n>: lines for per-tool lists"
    if [[ -n "$OLD_PRESETS" ]]; then
      echo "$OLD_PRESETS"
    else
      echo "presets: Standby:150, PLA:215, PETG:240, ABS:255"
      echo "#presets_t1: Standby:160, PETG:240, ASA:255"
    fi
    echo "log_length: 20"
    if [[ -n "$OLD_SAVEVARS" ]]; then
      echo
      echo "$OLD_SAVEVARS"
    elif [[ $ADD_SAVEVARS -eq 1 ]]; then
      echo
      echo "[save_variables]"
      echo "filename: ${CONFIG_DIR}/variables.cfg"
    fi
  } > "$DASH_CFG"
fi

if ! grep -qE '^\[include btc_dashboard\.cfg\]' "$PRINTER_CFG"; then
  info "Adding [include btc_dashboard.cfg] to printer.cfg (backup kept)"
  backup "$PRINTER_CFG"
  { echo "[include btc_dashboard.cfg]"; cat "$PRINTER_CFG"; } > "${PRINTER_CFG}.tmp" && mv "${PRINTER_CFG}.tmp" "$PRINTER_CFG"
fi

# ---------------------------------------------------------------- BTC tool limit
BTC_CFG="$(grep -rlE '^\[delayed_gcode start_check_carriage\]' "$CONFIG_DIR" --include='*.cfg' 2>/dev/null | head -n1 || true)"
if [[ -n "$BTC_CFG" ]] && grep -q "for tools in range(6)" "$BTC_CFG"; then
  N="$FOUND_TOOLS"; [[ "$TOOLS" =~ ^[0-9]+$ ]] && N="$TOOLS"
  if [[ "$N" -gt 6 ]]; then
    warn "Your BTC macros only register tools T0-T5 at startup: 'for tools in range(6)' in ${BTC_CFG}."
    echo "   The fix changes that one line to range(16). A backup is kept next to the file."
    echo "   Updating or re-copying BTC's files puts range(6) back; run ./install.sh again after that."
    if yesno "Patch ${BTC_CFG##*/} so T6 and up work?" y; then
      backup "$BTC_CFG"; sed -i 's/for tools in range(6)/for tools in range(16)/' "$BTC_CFG"
      info "Patched ${BTC_CFG} (backup: ${BTC_CFG}.btcdash-${STAMP}.bak)"
    fi
  fi
fi

# ---------------------------------------------------------------- moonraker update manager
if [[ -f "$MOONRAKER_CONF" ]] && ! grep -qE '^\[update_manager btc_dashboard\]' "$MOONRAKER_CONF"; then
  ORIGIN="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || true)"
  if [[ -n "$ORIGIN" ]]; then
    info "Adding update manager entry to moonraker.conf"
    backup "$MOONRAKER_CONF"
    cat >> "$MOONRAKER_CONF" <<EOF

[update_manager btc_dashboard]
type: git_repo
path: ${REPO_DIR}
origin: ${ORIGIN}
primary_branch: main
managed_services: klipper
EOF
  else
    warn "Not a git clone - skipping Moonraker update manager (clone from git to get updates in Mainsail)."
  fi
fi

# ---------------------------------------------------------------- Mainsail / Fluidd builds
# The ready-built zips live on the GitHub release (see ui-builds.conf) and are downloaded on demand.
source "${REPO_DIR}/ui-builds.conf"
for UI in mainsail fluidd; do
  [[ -d "${HOME}/${UI}" ]] || continue
  if [[ "$UI" == mainsail ]]; then UI_NAME="Mainsail"; UI_ZIP="$MAINSAIL_ZIP"; else UI_NAME="Fluidd"; UI_ZIP="$FLUIDD_ZIP"; fi
  echo
  info "${UI_NAME} build with the Toolchanger panel: ${UI_ZIP} (release ${RELEASE_TAG})"
  echo "   This replaces ~/${UI} with that ${UI_NAME} version. The official one is backed up first;"
  echo "   undo with: ${UI}/install_${UI}_build.sh --restore"
  if yesno "Install it into ~/${UI}?" y; then
    bash "${REPO_DIR}/scripts/install_ui_build.sh" "$UI" || warn "${UI_NAME} build not installed - see the message above."
  fi
done

# ---------------------------------------------------------------- standalone page (nginx)
if command -v nginx >/dev/null 2>&1; then
  if yesno "Also serve the standalone page on port ${PORT} (for other browsers or screens)?" n; then
    SITE="/etc/nginx/sites-available/btc-dashboard"
    TMP="$(mktemp)"
    sed -e "s#__PORT__#${PORT}#g" -e "s#__ROOT__#${REPO_DIR}/www#g" -e "s#__MOONRAKER__#${MOONRAKER_PORT}#g" \
      "${REPO_DIR}/nginx/btc-dashboard.conf" > "$TMP"
    info "Installing nginx site (needs sudo)"
    sudo cp "$TMP" "$SITE"; rm -f "$TMP"
    sudo ln -sf "$SITE" /etc/nginx/sites-enabled/btc-dashboard
    # nginx runs as www-data and must be able to read the page
    chmod o+x "$HOME" "$REPO_DIR" "$REPO_DIR/www" 2>/dev/null || true
    chmod o+r "$REPO_DIR"/www/* 2>/dev/null || true
    sudo nginx -t && sudo systemctl reload nginx
  fi
else
  warn "nginx not found. Serve ${REPO_DIR}/www any way you like and open it with ?moonraker=<host>:${MOONRAKER_PORT}"
fi

# ---------------------------------------------------------------- restart
if yesno "Restart Klipper now?" y; then
  if systemctl cat klipper.service >/dev/null 2>&1; then
    sudo systemctl restart klipper
  else
    warn "klipper.service not found - restart Klipper from Mainsail."
  fi
fi
if [[ -f "$MOONRAKER_CONF" ]] && grep -q '^\[update_manager btc_dashboard\]' "$MOONRAKER_CONF"; then
  yesno "Restart Moonraker to load the update manager entry?" y && sudo systemctl restart moonraker || true
fi

HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
info "Done. Open Mainsail or Fluidd - the Toolchanger panel/card is on the dashboard."
[[ -f /etc/nginx/sites-enabled/btc-dashboard ]] && echo "   Standalone page: http://${HOST:-<printer-ip>}:${PORT}/"
echo "   Check what was found with the console command: BTC_DASHBOARD_STATUS"
