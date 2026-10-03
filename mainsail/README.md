# Toolchanger panel inside Mainsail

A **Toolchanger** panel for the Mainsail dashboard. It sits alongside Toolhead, Extruder and Temperatures, and you can move, collapse and hide it like any other panel. It works like Happy Hare's MMU panel:

- The **Klipper add-on** (`klippy/btc_dashboard.py`, installed by `../install.sh`) publishes `printer.btc_dashboard`.
- **Mainsail** shows the panel only when that object exists. If the add-on isn't loaded, the panel stays hidden.

> **Status:** tested against a simulated printer only, not yet on real hardware.

| File | What it is |
|---|---|
| `0001-feat-btc-toolchanger-…patch` | The code change, made against Mainsail's `develop` branch (v2.19.0) |
| `install_mainsail_build.sh` | Downloads the ready-built Mainsail 2.19.0 with the panel and swaps it in and out of `~/mainsail` |
| `screenshots/` | The panel, the tool dialog and the spool picker |

The ready-built zip itself is attached to the [GitHub release](https://github.com/JeandreCoetzer/ToolChangerDashboard/releases), not stored in the repo.

## What the panel does

- **Tool tiles:** one picture per hotend, showing the filament colour, temperature (`215/215°` or `26° off`) and hotend fan speed. The active tool is highlighted in your Mainsail theme colour.
- **Header:** a chip showing *T1 active* or *Carriage empty*.
- **Status line:** carriage switch (with a warning if it disagrees with BTC), Dockslide state, number of toolchanges, and the last change's time and result.
- **Action buttons:** *Check tool*, *Sanity check*, *Home dockslide* (only with Dockslide) and *Drop off Tn*. These are locked while printing.
- **Tool dialog:** click a tile to open it.
  - Temperature presets for that tool from `btc_dashboard.cfg` (see the main README), a **Spool** button with the Spoolman filament temperature, and a box to type a target.
  - X/Y/Z offsets, saved through `BTC_DASHBOARD_SET_OFFSET`.
  - Filament: *Change spool* opens Mainsail's own Spoolman picker. Without Spoolman you set a material and colour instead.
  - **Select Tn** button, which runs `Tn`.
- **Settings (gear icon):** tiles per row and show/hide for the status line, action buttons and log. They're stored with the rest of Mainsail's settings in Moonraker.

## Option A: use the ready-built copy (quickest)

`../install.sh` offers this when it finds `~/mainsail`. To do it on its own:

```bash
cd ~/btc-dashboard
./mainsail/install_mainsail_build.sh             # downloads the build, backs up ~/mainsail, keeps your config.json
./mainsail/install_mainsail_build.sh --restore   # puts the official Mainsail back
```

Reload Mainsail with Ctrl+Shift+R. If the panel doesn't appear straight away, open **Settings → Dashboard** and make sure *Toolchanger* is switched on.

Updating Mainsail from the Update Manager puts the official build back, and the panel disappears until you run the script again. Option B avoids that.

## Option B: your own fork of Mainsail, with normal updates

1. On GitHub, fork `mainsail-crew/mainsail`, then apply the patch to your fork:
   ```bash
   git clone https://github.com/<your-github-user>/mainsail.git && cd mainsail
   git checkout develop
   git am ~/btc-dashboard/mainsail/0001-*.patch
   npm ci && npm run build          # makes dist/mainsail.zip
   ```
2. Create a GitHub release on your fork, for example `v2.19.0-btc1`, and attach `dist/mainsail.zip` to it, the same way official Mainsail releases do.
3. In `moonraker.conf`, point Mainsail's update entry at your fork:
   ```ini
   [update_manager mainsail]
   type: web
   channel: stable
   repo: <your-github-user>/mainsail
   path: ~/mainsail
   ```

When Mainsail puts out a new version, merge it into your fork, rebuild and make a new release. The Update Manager will then offer it to you.

## Option C: official Mainsail

The long-term goal is to get the panel into official Mainsail, so every BTC user gets it with normal updates. Progress on that is tracked in [CONTRIBUTING.md](../CONTRIBUTING.md#getting-the-panel-into-mainsail-and-fluidd).

## What it was checked against

- Mainsail `develop` at v2.19.0 (26 Sep 2026): `npm run lint`, `npm run format:check`, `npm run test:unit` (46 tests) and `npm run build` all pass.
- The full Mainsail build running against a simulated Moonraker (`../tests/mock_moonraker_mainsail.py`), which runs the real `btc_dashboard.py` on a fake 8-tool BTC printer with Spoolman. The screenshots come from that run.
- Only English text is included. Mainsail falls back to English for other languages until someone translates it.
