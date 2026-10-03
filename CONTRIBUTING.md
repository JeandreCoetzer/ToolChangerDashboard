# Contributing

Thanks for helping. Bug reports from real printers are the most useful thing right now, because so far the dashboard has only run against a simulated one. Please include the output of `BTC_DASHBOARD_STATUS` and, for a crash, the traceback from `~/printer_data/logs/klippy.log`.

## Layout

| Part | Where | Checks |
|---|---|---|
| Klipper add-on | `klippy/btc_dashboard.py` | `python3 tests/test_klippy.py` |
| Standalone page | `www/` | `tests/mock_moonraker.py` + `tests/ui_check.py` (see the README) |
| Mainsail panel | `mainsail/0001-*.patch`, applied to Mainsail `develop` | `npm run lint`, `npm run format:check`, `npm run test:unit`, `npm run build` |
| Fluidd card | `fluidd/0001-*.patch`, applied to Fluidd `develop` | `pnpm run lint`, `type-check`, `test:unit`, `circular-check`, `build` |
| Installers | `install.sh`, `uninstall.sh`, `scripts/install_ui_build.sh` | dry-run them against a scratch `HOME` (they accept `-k` and `-d`) |

The add-on is the contract between the parts: Mainsail, Fluidd and the standalone page all read `printer.btc_dashboard`. If you add a field there, add it to the typings in both patches (`BtcStatus` in Mainsail's mixin, `Klipper.BtcDashboardState` in Fluidd) and keep older fields working, because people may run a new add-on with an old UI build or the other way round.

## Rebuilding the Mainsail and Fluidd builds

The ready-built zips are release assets, not files in the repo.

1. Apply the patch to the matching upstream version, build, and zip the `dist/` folder (Mainsail's `npm run build` makes `dist/mainsail.zip` itself).
2. Name the zips `mainsail-btc-toolchanger-<mainsail version>.zip` and `fluidd-btc-toolchanger-<fluidd version>.zip`.
3. Update `ui-builds.conf`: the release tag, the zip names and their `sha256sum`.
4. Commit, tag the commit with the same release tag, and attach both zips to that GitHub release.

The install scripts download from the tag in `ui-builds.conf` and refuse a zip whose checksum doesn't match.

## Getting the panel into Mainsail and Fluidd

The long-term aim is for both projects to ship the panel, the way Happy Hare's MMU panel is shipped, so nobody needs a modified build. Neither has been asked yet. The plan:

1. Test on a real printer and take screenshots, including a phone screenshot.
2. Open a feature-request issue on each project describing the panel, linking this repo, and ask whether they'd accept it.
3. Only then open the pull requests. Draft descriptions are in [`docs/upstream/`](docs/upstream).

Each project has its own rules:

- **Mainsail** only accepts pull requests from contributors on its vouched list; others are closed automatically. Getting to know the maintainers in the issue or on their Discord comes first. PRs go against `develop` with a Conventional Commit title.
- **Fluidd** enforces a commit subject of 50 characters or fewer and pull requests from a feature branch; for a whole new card it's worth discussing it with the maintainers first.
- **Both** require every commit to be signed off under the Developer Certificate of Origin. The commits in the patches here are not signed off: the sign-off is the submitter's own statement, so add it yourself with `git commit --amend -s` before pushing.
- Mainsail's pull request template asks for AI assistance to be disclosed. The drafts in `docs/upstream/` say so for both projects.

## Licence

By contributing you agree that your contribution is licensed under the GNU GPL v3, like the rest of the project.
