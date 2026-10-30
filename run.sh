#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
exec /usr/bin/python3 -m bale_desktop.app "$@"
