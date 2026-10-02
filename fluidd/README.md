# Toolchanger card inside Fluidd

This folder contains a **Toolchanger** card for the Fluidd dashboard. It works the same way as the Mainsail panel (see [`../mainsail/README.md`](../mainsail/README.md)) and the way Fluidd's own MMU and AFC cards work: the card only appears when the Klipper add-on publishes `printer.btc_dashboard`. You can drag, collapse and hide it like any other card in Fluidd's layout mode.

| File | What it is |
|---|---|
| `0001-feat-add-BTC-toolchanger-card.patch` | The code change, made against Fluidd's `develop` branch (v1.37.6) |
| `fluidd-btc-toolchanger-1.37.6.zip` | A ready-built Fluidd 1.37.6 with the card included |
| `install_fluidd_build.sh` | Swaps the built copy in and out of `~/fluidd` |
| `screenshots/` | The card, the tool dialog and the spool picker |

## What the card does

It has the same features as the Mainsail panel:

- **Tool tiles:** one picture per hotend, showing the filament colour, temperature and hotend fan speed. The active tool is highlighted in your Fluidd theme colour.
- **Header:** a chip showing *T1 active* or *Carriage empty*.
- **Status line:** carriage switch, Dockslide state, number of toolchanges, and the last change's time and result.
- **Action buttons:** *Check tool*, *Sanity check*, *Home dockslide* and *Drop off Tn*. These are locked while printing.
- **Tool dialog:** click a tile to open it.
  - Temperature presets for that tool, from `btc_dashboard.cfg` (see the main README), plus a **Spool** button with the Spoolman filament temperature, and a box to type a target.
  - X/Y/Z offsets.
  - Filament: *Change spool* opens Fluidd's own **Spool Selection** dialog for that tool, which saves the spool through `SET_GCODE_VARIABLE` and `SAVE_VARIABLE`.
  - **Select Tn** button, which runs `Tn`.
- **Settings (gear icon):** tiles per row and show/hide for the status line, action buttons and log. They're stored in Fluidd's settings in Moonraker.

## Option A: use the ready-built copy

After running `../install.sh` for the Klipper add-on:

```bash
cd ~/btc-dashboard/fluidd
bash install_fluidd_build.sh              # backs up ~/fluidd, installs the build, keeps your config.json
# bash install_fluidd_build.sh --restore  # puts the official Fluidd back
```

`../install.sh` offers this step itself when it finds `~/fluidd`. Reload Fluidd with Ctrl+Shift+R.

**Catch:** updating Fluidd from the Update Manager puts the official build back. Run the script again afterwards, or use option B.

## Option B: your own copy of Fluidd on GitHub, with updates

1. On GitHub, fork `fluidd-core/fluidd`, then apply the patch:
   ```bash
   git clone https://github.com/JeandreCoetzer/fluidd.git && cd fluidd
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
   repo: JeandreCoetzer/fluidd
   path: ~/fluidd
   ```

## Option C: get it into official Fluidd

Fluidd's rules for contributions (from its `CONTRIBUTING.md` and `AGENTS.md`):

- **Discuss it first.** Open an issue, or talk on their Discord, describing the card and linking the add-on.
- **Every commit must be signed off.** The commit in the patch isn't signed off, because the sign-off is your statement that you have the right to contribute it. Run `git commit --amend -s` before pushing. Fluidd's commit hook also refuses a commit without a sign-off.
- **The commit subject must be 50 characters or fewer.** The one in the patch, `feat: add BTC toolchanger card`, already fits.
- **Pull requests come from a feature branch.** Their CI runs `lint`, `type-check`, `test:unit`, `circular-check` and `build`.

A draft pull request description is in `PR_DESCRIPTION.md`.

## What it was checked against

- Fluidd `develop` at v1.37.6 (29 Sep 2026):
  - `pnpm run lint`: no warnings
  - `pnpm run type-check`: clean
  - `pnpm run test:unit`: 507 tests passed
  - `pnpm run circular-check`: none found
  - `pnpm run build`: succeeded
- The Fluidd build running against a simulated Moonraker (`../tests/mock_moonraker_mainsail.py`), which runs the real `btc_dashboard.py` on a fake 8-tool BTC printer with Spoolman. The screenshots come from that run:
  - selecting T3 made it the active tool
  - *Change spool* opened Fluidd's spool dialog for the right tool
- **It has not yet been tested on a real printer.**
- Only English text is included. Fluidd manages other languages through Weblate, and they fall back to English until translated.
