#!/usr/bin/env bash
# Install the Fluidd build with the Toolchanger card, or --restore the official one.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../scripts/install_ui_build.sh" fluidd "$@"
