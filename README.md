# BTC Dashboard

A compact web panel for hotend-swapping toolchangers that run the **BTC (Bikin Toolchanger)** macros, such as [Lineux Hotswap](https://github.com/3dfiyMyLife/Lineux-Hotswap). It works along the lines of Happy Hare's MMU panel: a picture of each hotend with its temperature and fan speed. Click a hotend to get a popup where you can select that tool, set its temperature, change its spool and edit its offsets.

There are two ways to see it:

- **Inside Mainsail (recommended).** A *Toolchanger* panel on the Mainsail dashboard, like Happy Hare's MMU panel. See [`mainsail/README.md`](mainsail/README.md).
- **Inside Fluidd.** A *Toolchanger* card on the Fluidd dashboard. See [`fluidd/README.md`](fluidd/README.md).
- **Standalone page.** Its own page on port 8137. Useful for other browsers or a spare screen.

Both read the same Klipper add-on.

It doesn't change how BTC works. BTC keeps doing every move, check and toolchange. The dashboard only reads BTC's state and runs BTC's own commands.

```
btc-dashboard/
├── klippy/btc_dashboard.py      Klipper add-on: publishes printer.btc_dashboard
├── mainsail/                    Mainsail panel: patch, ready-built Mainsail, install script
├── fluidd/                      Fluidd card: patch, ready-built Fluidd, install script
├── www/                         Standalone page (plain HTML/CSS/JS, no build step)
├── config/btc_dashboard.cfg.example
├── nginx/btc-dashboard.conf     Serves the panel + proxies Moonraker
├── install.sh / uninstall.sh
└── tests/                       Offline tests (fake Klipper + mock Moonraker)
```

## Install

On the printer's Pi, as your normal user:

```bash
cd ~
git clone https://github.com/JeandreCoetzer/ToolChangerDashboard.git ~/btc-dashboard
cd ~/btc-dashboard
chmod +x install.sh uninstall.sh mainsail/*.sh fluidd/*.sh
./install.sh
```

The installer finds your tools and asks a few questions. Each one has a sensible default:

| Question | Options | Default |
|---|---|---|
| How many tools | `auto` or a number | `auto`, meaning every `_VARIABLES_Tn` macro it finds |
| Dock sense switches | `none` / `per_tool` | `none`, since Lineux only has the carriage switch |
| Carriage switch name | a gcode_button name | `carriage_sense` |
| Dockslide | `auto` / `yes` / `no` | `auto`, meaning on if `DOCKSLIDE_HOME` exists |
| Spoolman | `auto` / `yes` / `no` | `auto`, meaning on if Moonraker has `[spoolman]` |
| Keep edited offsets after restart | y / n | y (adds `[save_variables]` if you don't have one) |

Then it:

1. Links `btc_dashboard.py` into `~/klipper/klippy/extras/`.
2. Writes `~/printer_data/config/btc_dashboard.cfg` and adds `[include btc_dashboard.cfg]` to the top of `printer.cfg`. A backup is kept.
3. Adds `[update_manager btc_dashboard]` to `moonraker.conf`, so updates show up in Mainsail's update screen. This only works if you installed with `git clone`.
4. Offers to install the Mainsail and/or Fluidd build that includes the Toolchanger panel, for whichever of `~/mainsail` and `~/fluidd` exist. The official build is backed up first; see [`mainsail/README.md`](mainsail/README.md) and [`fluidd/README.md`](fluidd/README.md).
5. Optionally installs an nginx site on port **8137** for the standalone page.
6. If you have more than 6 tools, it offers to patch BTC's startup loop, which only registers T0–T5 (`range(6)`).
7. Restarts Klipper.

Open Mainsail or Fluidd. The Toolchanger panel is on the dashboard: in Mainsail, move it under Settings → Dashboard; in Fluidd, use the dashboard's layout mode. Run `BTC_DASHBOARD_STATUS` in the console to see what it found.

`./install.sh -y` skips the questions and uses the defaults. `-k`, `-d`, `-p` and `-m` change the Klipper folder, printer_data folder, panel port and Moonraker port.

### Without nginx

Serve `www/` any way you like and point it at Moonraker with a query string, for example `http://host:8000/?moonraker=192.168.1.50:7125`. Moonraker must allow that origin in `cors_domains`.

## Where the data comes from

| Panel shows | Klipper source |
|---|---|
| Active tool | `gcode_macro _BTC_VARIABLES.tool_current_asperbtc` |
| Offsets, input shaper, pressure advance | `gcode_macro _VARIABLES_Tn` |
| Temperature and target | `extruder`, `extruder1`, … (taken from each `Tn` macro's `ACTIVATE_EXTRUDER`) |
| Hotend fan | the `heater_fan` whose `heater:` is that extruder |
| Spool | `gcode_macro Tn.spool_id`, with details from Spoolman through Moonraker |
| Carriage | `gcode_button carriage_sense` |
| Dock sensors | `gcode_button dock_sense_t{n}` (only when `dock_sense: per_tool`) |
| Dockslide | `gcode_macro _DOCKSLIDE_VARIABLES.dockslide_status`, endstop buttons |
| Toolchange log and times | recorded by the add-on (see below) |

**Toolchange timing.** The add-on wraps `TOOL_PICKUP` and `TOOL_DROPOFF`. The originals still run unchanged; the wrapper just notes the start and end, then checks the result:

- **Pickup:** the tool must be registered on the carriage afterwards.
- **Dropoff:** `last_dropoff_successful` must be set and the carriage must be empty afterwards.

Durations use Klipper's motion clock, so they include the move time and any reheat wait.

**Offsets.** "Save" in the popup runs `BTC_DASHBOARD_SET_OFFSET TOOL=n X= Y= Z=`. That updates `_VARIABLES_Tn` straight away, and applies the new offset if that tool is on the carriage and no print is running. With `save_offsets` on, the values also go into `[save_variables]` and come back after a restart. They **override** the numbers in `tool_n.cfg`, and the console says so at startup. To go back to the cfg values, run `BTC_DASHBOARD_CLEAR_SAVED_OFFSETS` and restart.

**Filament without Spoolman.** With `spoolman: no`, the popup lets you set a material and colour for each tool. These are stored in Moonraker's database.

## Commands

| Command | What it does |
|---|---|
| `BTC_DASHBOARD_STATUS` | Lists the tools found and how each was mapped, plus any warnings |
| `BTC_DASHBOARD_SET_OFFSET TOOL=1 X=-0.12 Y=0.35 Z=0.04 [SAVE=0]` | Sets a tool's offsets (`SAVE=0` = until restart only) |
| `BTC_DASHBOARD_CLEAR_SAVED_OFFSETS` | Forgets the saved offsets |
| `BTC_DASHBOARD_RESET_STATS` | Clears the counters and the log |

The panel itself runs BTC's own commands: `Tn`, `TOOL_DROPOFF`, `CHECK_CARRIAGE`, `SANITY_CHECK_TOOLS`, `DOCKSLIDE_HOME` and `SET_HEATER_TEMPERATURE`. Tool changes, offset edits and the action buttons are locked while printing. Temperatures can still be set during a print.

## Panel settings

The gear icon opens the panel settings: tiles per row, whether to show the status line and the log, and whether to ask before changing tools. Temperature presets are set in the Klipper config instead (see below). They're saved in Moonraker's database (namespace `btc_dashboard`), so every browser sees the same settings for that printer.

## Temperature presets (per tool)

Each tool's popup shows preset buttons from the Klipper config. Edit `btc_dashboard.cfg`:

```ini
[btc_dashboard]
presets: Standby:150, PLA:215, PETG:240        # every tool without its own list
presets_t2: Standby:160, PETG:240, ASA:255     # T2 only
presets_t3: Standby:0, TPU:225                 # T3 only
```

You can also put a list in the tool's own file, where it takes priority over both of the above:

```ini
[gcode_macro _VARIABLES_T3]
variable_temp_presets: "Standby:0, TPU:225"
```

Restart Klipper after a change. `BTC_DASHBOARD_STATUS` lists each tool's presets and where they came from. The popup also says where its presets came from, so you know which line to edit.

If a preset is badly written, or hotter than that heater's `max_temp`, it is left out and a warning appears on the panel. When the tool has a Spoolman spool, an extra **Spool** button uses the filament's print temperature from Spoolman.

## Config reference

See [`config/btc_dashboard.cfg.example`](config/btc_dashboard.cfg.example). If your heaters or fans don't follow BTC's naming, set `extruder_names` and `hotend_fan_names` (comma-separated, in tool order).

## Testing without a printer

```bash
python3 tests/test_klippy.py                 # add-on against a fake Klipper
pip install websockets playwright
TOOLS=8 python3 tests/mock_moonraker.py &    # fake Moonraker on :7125
(cd www && python3 -m http.server 8137 &)
python3 tests/ui_check.py /tmp               # screenshots of the panel
```

## Uninstall

`./uninstall.sh` removes the add-on link, the nginx site, the include line and the update manager entry. It renames `btc_dashboard.cfg` instead of deleting it and keeps backups of every file it edits.

## Limitations

- The Mainsail panel and Fluidd card come as modified builds until each project accepts them. Updating Mainsail or Fluidd from the Update Manager replaces the modified build with the official one. See the `mainsail/` and `fluidd/` READMEs for how to avoid that.
- The tool must still be tracked by BTC. The carriage switch can tell a tool is on, but not which one.
