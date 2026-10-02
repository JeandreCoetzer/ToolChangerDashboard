# Toolchanger panel inside Mainsail

This folder contains a **Toolchanger** panel for the Mainsail dashboard. It sits alongside Toolhead, Extruder and Temperatures, and you can move, collapse and hide it like any other panel. It works the same way as Happy Hare's MMU panel:

- The **Klipper add-on** (`klippy/btc_dashboard.py`, installed by `../install.sh`) publishes `printer.btc_dashboard`.
- **Mainsail** shows the panel only when that object exists. If the add-on isn't loaded, the panel doesn't show.

| File | What it is |
|---|---|
| `0001-feat-btc-toolchanger-…patch` | The code change, made against Mainsail's `develop` branch (v2.19.0) |
| `mainsail-btc-toolchanger-2.19.0.zip` | A ready-built Mainsail 2.19.0 with the panel included |
| `install_mainsail_build.sh` | Swaps the built copy in and out of `~/mainsail` |
| `screenshots/` | The panel, the tool dialog and the spool picker |

## What the panel does

- **Tool tiles:** one picture per hotend, showing the filament colour, temperature (`215/215°` or `26° off`) and hotend fan speed. The active tool is highlighted in your Mainsail theme colour.
- **Header:** a chip showing *T1 active* or *Carriage empty*.
- **Status line:** carriage switch (with a warning if it disagrees with BTC), Dockslide state, number of toolchanges, and the last change's time and result.
- **Action buttons:** *Check tool*, *Sanity check*, *Home dockslide* (only with Dockslide) and *Drop off Tn*. These are locked while printing.
- **Tool dialog:** click a tile to open it.
  - Temperature presets for that tool, from `btc_dashboard.cfg` (see the main README), plus a **Spool** button with the Spoolman filament temperature, and a box to type a target.
  - X/Y/Z offsets, saved through `BTC_DASHBOARD_SET_OFFSET`.
  - Filament: *Change spool* opens Mainsail's own Spoolman picker. Without Spoolman you set a material and colour instead.
  - **Select Tn** button, which runs `Tn`.
- **Settings (gear icon):** tiles per row and show/hide for the status line, action buttons and log. They're stored with the rest of Mainsail's settings in Moonraker.

## Option A: use the ready-built copy (quickest)

On the Pi, after running `../install.sh` for the Klipper add-on:

```bash
cd ~/btc-dashboard/mainsail
./install_mainsail_build.sh              # backs up ~/mainsail, installs the build, keeps your config.json
# ./install_mainsail_build.sh --restore  # puts the official Mainsail back
```

Reload Mainsail with Ctrl+Shift+R. If the panel doesn't appear straight away, open **Settings → Dashboard** and make sure *Toolchanger* is switched on.

**Catch:** updating Mainsail from the Update Manager puts the official build back. The panel then disappears until you run the script again. To avoid that, use option B.

## Option B: your own copy of Mainsail on GitHub, with updates

1. On GitHub, fork `mainsail-crew/mainsail`, then apply the patch:
   ```bash
   git clone https://github.com/JeandreCoetzer/mainsail.git && cd mainsail
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
   repo: JeandreCoetzer/mainsail
   path: ~/mainsail
   ```
When Mainsail puts out a new version, merge it into your fork, rebuild and make a new release. The Update Manager will then offer it to you.

## Option C: get it into official Mainsail

This is the long-term fix: every BTC/Lineux user gets the panel with normal Mainsail updates. Mainsail has two rules to know about first:

- **Only "vouched" contributors can open pull requests.** Pull requests from anyone else are closed automatically (see `CONTRIBUTING.md` → *Contributor Trust*). So start by opening an **issue** that describes the panel, with screenshots and a link to the add-on. Talk with the maintainers there or on their Discord.
- **Pull requests go against `develop`,** with a Conventional Commit title, and every commit must be **signed off** under the DCO. The commit in the patch isn't signed off, because the sign-off is your statement that you have the right to contribute it. Before you push, run `git commit --amend -s`.

A draft pull request description is in `PR_DESCRIPTION.md`. It already includes the line their template asks for when an AI tool helped write the change.

## What it was checked against

- Mainsail `develop` at v2.19.0 (26 Sep 2026): `npm run lint`, `npm run format:check`, `npm run test:unit` (46 tests passed) and `npm run build` all pass.
- A full Mainsail build running against a simulated Moonraker (`../tests/mock_moonraker_mainsail.py`). That simulation runs the real `btc_dashboard.py` on a fake 8-tool BTC printer with Spoolman. The screenshots come from that run.
- **It has not yet been tested on a real printer.**
- Only English text is included. Mainsail falls back to English for other languages until someone translates it.
