#!/usr/bin/env bash

set -euo pipefail

if command -v flatpak-spawn >/dev/null 2>&1; then
  exec flatpak-spawn --host podman "$@"
fi

exec podman "$@"
