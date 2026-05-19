#!/usr/bin/env bash
# Reset Cynthion to Apollo bootloader mode (1d50:60e6).
# Works even when the moondancer interface is unresponsive after a proxy crash.
#
# Uses ApolloDebugger(force_offline=True): requests USB handoff from the FPGA
# stub interface, then lets Apollo reconfigure the FPGA from config flash.
# The device comes back in analyzer mode (subclass 0x10) — run
# `cynthion run facedancer` to reload facedancer gateware.
#
# Run from repo root: ./scripts/reset-cynthion.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/venv"

if [ ! -f "$VENV/bin/python" ]; then
    echo "venv not found — run ./scripts/setup-venv.sh first"
    exit 1
fi

if ! lsusb | grep -q "1d50:"; then
    echo "No Cynthion detected on USB (expected 1d50:60e6 or 1d50:615b)."
    exit 1
fi

echo "Requesting soft reset via Apollo debugger..."
"$VENV/bin/python" - <<'EOF'
from apollo_fpga import ApolloDebugger
device = ApolloDebugger(force_offline=True)
device.soft_reset()
device.allow_fpga_takeover_usb()
device.close()
print("Reset complete.")
EOF
