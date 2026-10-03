**Title:** `feat(btc-toolchanger): add panel for BTC hotend toolchangers`

## Description

This PR adds a dashboard panel for hotend-swapping toolchangers that run the BTC (Bikin Toolchanger) macros, such as [Lineux Hotswap](https://github.com/3dfiyMyLife/Lineux-Hotswap).

- Each hotend is shown as a tile with its filament colour, temperature and hotend fan speed. The active tool is highlighted in the theme's primary colour.
- A status line shows the carriage switch (and flags when it disagrees with BTC), the Dockslide state, the toolchange count and the last change's result.
- Clicking a tile opens a tool dialog. From there you can select the tool (`Tn`), set its temperature, edit its X/Y/Z offsets, and assign a Spoolman spool. The spool picker reuses `SpoolmanChangeSpoolDialog`, so the spool is saved on the `Tn` macro, in `save_variables` and in `lane_data`, the same way Mainsail already does it.
- Temperature presets come per tool from the add-on (`tools[n].presets`), plus a Spoolman filament temperature button.
- Tool changes and offset edits are disabled while printing.
- Panel settings are stored under `gui.view.btcToolchanger`: tiles per row and whether to show the status line, action buttons and log.

The panel only appears when the `btc_dashboard` Klipper add-on is loaded, which publishes `printer.btc_dashboard`. This follows the same pattern as the MMU panel (`printer.mmu`) and the AFC panel (`printer.AFC`). Nothing changes for users without it.

Files changed:

- New: `BtcToolchangerPanel.vue`, the `BtcToolchanger/` subcomponents, and the `btcToolchanger` mixin.
- Registration: `allDashboardPanels`, `getAllPossiblePanels`, the panel icon, `Dashboard.vue`, the GUI defaults and types, and `en.json` strings.

## Related Tickets & Documents

- Klipper add-on: https://github.com/JeandreCoetzer/ToolChangerDashboard
- Feature request issue: <link once opened>

## Mobile & Desktop Screenshots/Recordings

<!-- attach screenshots/panel.png, screenshots/tool-dialog.png, screenshots/spool-dialog.png, plus a mobile screenshot from a real printer -->

## [optional] Are there any post-deployment tasks we need to perform?

None. Translations other than English fall back to `en` until they're added.

🤖 This Pull Request was created with the help of Claude.
