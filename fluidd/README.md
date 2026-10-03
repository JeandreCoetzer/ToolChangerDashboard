# Toolchanger card inside Fluidd

A **Toolchanger** card for the Fluidd dashboard. It works the same way as the [Mainsail panel](../mainsail/README.md) and Fluidd's own MMU and AFC cards: the card only appears when the Klipper add-on publishes `printer.btc_dashboard`. You can drag, collapse and hide it like any other card in Fluidd's layout mode.

> **Status:** tested against a simulated printer only, not yet on real hardware.

| File | What it is |
|---|---|
| `0001-feat-add-BTC-toolchanger-card.patch` | The code change, made against Fluidd's `develop` branch (v1.37.6) |
| `install_fluidd_build.sh` | Downloads the ready-built Fluidd 1.37.6 with the card and swaps it in and out of `~/fluidd` |
| `screenshots/` | The card, the tool dialog and the spool picker |

The ready-built zip itself is attached to the [GitHub release](https://github.com/JeandreCoetzer/ToolChangerDashboard/releases), not stored in the repo.

## What the card does

It has the same features as the Mainsail panel:

- **Tool tiles:** one picture per hotend, showing the filament colour, temperature and hotend fan speed. The active tool is highlighted in your Fluidd theme colour.
- **Header:** a chip showing *T1 active* or *Carriage empty*.
- **Status line:** carriage switch, Dockslide state, number of toolchanges, and the last change's time and result.
- **Action buttons:** *Check tool*, *Sanity check*, *Home dockslide* and *Drop off Tn*. These are locked while printing.
- **Tool dialog:** click a tile to open it.
  - Temperature presets for that tool from `btc_dashboard.cfg` (see the main README), a **Spool** button with the Spoolman filament temperature, and a box to type a target.
  - X/Y/Z offsets.
  - Filament: *Change spool* opens Fluidd's own **Spool Selection** dialog for that tool, which saves the spool through `SET_GCODE_VARIABLE` and `SAVE_VARIABLE`.
  - **Select Tn** button, which runs `Tn`.
- **Settings (gear icon):** tiles per row and show/hide for the status line, action buttons and log. They're stored in Fluidd's settings in Moonraker.

## Option A: use the ready-built copy

`../install.sh` offers this when it finds `~/fluidd`. To do it on its own:

```bash
cd ~/btc-dashboard
./fluidd/install_fluidd_build.sh             # downloads the build, backs up ~/fluidd, keeps your config.json
./fluidd/install_fluidd_build.sh --restore   # puts the official Fluidd back
```

Reload Fluidd with Ctrl+Shift+R. Updating Fluidd from the Update Manager puts the official build back; run the script again afterwards, or use option B.

## Option B: your own fork of Fluidd, with normal updates

1. On GitHub, fork `fluidd-core/fluidd`, then apply the patch to your fork:
   ```bash
   git clone https://github.com/<your-github-user>/fluidd.git && cd fluidd
   git checkout develop && git checkout -b feat/btc-toolchanger-card
   git am ~/btc-dashboard/fluidd/0001-*.patch
   pnpm i && pnpm run build        # needs pnpm 12 and Node 24
   ```
2. Zip the contents of `dist/` as `fluidd.zip` and attach it to a GitHub release on your fork.
3. In `moonraker.conf`, point Fluidd's update entry at your fork:
   ```ini
   [update_manager fluidd]
   type: web
   channel: stable
   repo: <your-github-user>/fluidd
   path: ~/fluidd
   ```

## Option C: official Fluidd

The long-term goal is to get the card into official Fluidd. Progress on that is tracked in [CONTRIBUTING.md](../CONTRIBUTING.md#getting-the-panel-into-mainsail-and-fluidd).

## What it was checked against

- Fluidd `develop` at v1.37.6 (29 Sep 2026): `pnpm run lint` (no warnings), `pnpm run type-check`, `pnpm run test:unit` (507 tests), `pnpm run circular-check` and `pnpm run build` all pass.
- The Fluidd build running against a simulated Moonraker (`../tests/mock_moonraker_mainsail.py`), which runs the real `btc_dashboard.py` on a fake 8-tool BTC printer with Spoolman. The screenshots come from that run.
- Only English text is included. Fluidd manages other languages through Weblate, and they fall back to English until translated.
