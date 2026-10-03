#!/usr/bin/env bash
# Install the Mainsail build with the Toolchanger panel, or --restore the official one.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/install_ui_build.sh" mainsail "$@"
