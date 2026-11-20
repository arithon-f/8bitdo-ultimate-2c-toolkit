# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller's battery over Bluetooth, as macOS reports it: GameController doesn't give it for an Xbox identity, and
the public power source API lists only the Mac's own battery, so this reads pmset, which lists accessories too."""
import plistlib
import re
import subprocess
import sys


def bluetooth_percent(name: str) -> int | None:
    """The level macOS shows for the accessory with this name, or None."""
    if sys.platform != "darwin":
        return None
    try:
        raw = subprocess.run(["/usr/bin/pmset", "-g", "accps", "-xml"], capture_output=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for doc in re.split(rb"(?=<\?xml)", raw):   # one plist per power source
        try:
            source = plistlib.loads(doc)
        except Exception:
            continue
        for item in source if isinstance(source, list) else [source]:
            if isinstance(item, dict) and item.get("Name") == name and isinstance(item.get("Current Capacity"), int):
                return item["Current Capacity"]
    return None
