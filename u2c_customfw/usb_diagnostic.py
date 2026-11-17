# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only normal-mode controller diagnostic (stock and Xbox-compatible)."""
import logging
import os

from .ops.devices import find
from .transport import open_channel
from .protocol import app


def main():
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    devices = [d for d in find() if d.mode in ("cable", "cable_360")]
    if len(devices) != 1:
        raise SystemExit(f"Expected one USB controller, found {len(devices)}")
    print("Controller mode:", devices[0].mode)
    if devices[0].mode == "cable_360":
        print("Output transport:", os.environ.get("U2C_USB_OUTPUT", "interrupt"))
    else:
        print("Output transport: hidraw (stock mode)")
    ch = open_channel(devices[0].info, 0x81)
    try:
        result = app.read(ch, 0x10000, 16, tries=1)
        print("Read result:", "SUCCESS (16 bytes)" if result is not None else "NO VALID RESPONSE")
    finally:
        ch.close()


if __name__ == "__main__":
    main()
