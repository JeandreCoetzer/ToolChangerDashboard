**Title:** `feat: add BTC toolchanger card`

## Description

This PR adds a dashboard card for hotend-swapping toolchangers that run the BTC (Bikin Toolchanger) macros, such as [Lineux Hotswap](https://github.com/3dfiyMyLife/Lineux-Hotswap).

- Each hotend is shown as a tile with its filament colour, temperature and hotend fan speed. The active tool is highlighted in the theme's primary colour.
- A status line shows the carriage switch (and flags when it disagrees with BTC), the Dockslide state, the toolchange count and the last change's result.
- Clicking a tile opens a dialog. From there you can select the tool (`Tn`), set its temperature, and edit its offsets.
- **Change spool** reuses the existing Spool Selection dialog via `spoolman/setDialogState` with `targetMacro`, so spool assignment works exactly as it does elsewhere in Fluidd.
- Temperature presets come per tool from the add-on (`tools[n].presets`), plus a Spoolman filament temperature button.
- Tool changes and offset edits are disabled while printing.
- Card settings live in `uiSettings.btcToolchanger` and are saved with `config/saveByPath`.

The card is hidden unless the `btc_dashboard` Klipper add-on is loaded, which publishes `printer.btc_dashboard`. It is filtered in `Dashboard.vue` the same way as `mmu-card` and `afc-card`. Nothing changes for other users.

Files changed:

- New: `widgets/btc-toolchanger/*` and `mixins/btcToolchanger.ts`.
- Typings: `Klipper.BtcDashboardState`.
- Registration: the layout default, the config defaults and types, the `btcToolchanger` icon, and the `en.yaml` strings.

Checks: `lint`, `type-check`, `test:unit`, `circular-check` and `build` all pass.

## Related

- Klipper add-on: https://github.com/JeandreCoetzer/ToolChangerDashboard
- Discussion/issue: <link>

## Screenshots

<!-- attach screenshots/card.png, screenshots/tool-dialog.png, screenshots/spool-dialog.png, plus a phone screenshot from a real printer -->

This change was created with the help of Claude.
