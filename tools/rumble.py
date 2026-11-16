#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Developer tool: send one Xbox rumble report to the controller over Bluetooth from this Mac, and nothing after it (no
stop), to see how the firmware times it. Then press Enter when the vibration ends to get its length.

    PYTHONPATH=. python3 tools/rumble.py STRONG WEAK DURATION [--loops N] [--delay D] [--mask M] [--stop-after MS]

STRONG and WEAK are Xbox magnitudes, 0-100. DURATION and --delay are in 10 ms units, 0-255. --loops is 0-255: the
motors run for DURATION, then that many times more. --mask is the enable mask (default 3, both main motors; 128 is the
Home ring command). --stop-after sends a stop that many milliseconds later, as a browser or game does at the end of an effect.
The controller must be connected to this Mac with the Xbox tweak, and the terminal needs Input Monitoring.

    rumble.py 100 100 255 --loops 255   Android's long request: 2.55 s with Rumble over Bluetooth, 652.8 s with Long rumble
    rumble.py 100 100 100 --loops 4     1 s, then 4 times more: 1 s with Rumble over Bluetooth, 5 s with Long rumble
    rumble.py 100 100 100 --delay 50    1 s after a 0.5 s delay: the firmware ignores the delay, so it starts at once
    rumble.py 0 0 0                     stop
    rumble.py 100 100 5                 50 ms on its own
    rumble.py 100 100 255 --loops 255 --stop-after 50
                                        a 50 ms tap as a browser sends it: the longest request, then a stop 50 ms later
"""
import argparse
import ctypes as C
import sys
import time

from u2c_customfw.transport import iokit


def upto(top):
    def parse(s):
        v = int(s, 0)
        if not 0 <= v <= top:
            raise argparse.ArgumentTypeError(f"{s} isn't 0-{top}")
        return v
    return parse


def main():
    ap = argparse.ArgumentParser(description="Send one Xbox rumble report over Bluetooth, with no stop after it.")
    for name, top in (("strong", 100), ("weak", 100), ("duration", 255)):
        ap.add_argument(name, type=upto(top), metavar=name.upper())
    ap.add_argument("--loops", type=upto(255), default=0, metavar="N", help="run DURATION, then N times more (0-255)")
    ap.add_argument("--delay", type=upto(255), default=0, metavar="D", help="start delay, 10 ms units (0-255)")
    ap.add_argument("--mask", type=lambda s: int(s, 0), default=3)
    ap.add_argument("--stop-after", type=int, metavar="MS", help="send a stop this many milliseconds later")
    a = ap.parse_args()
    pads = [d for d in iokit.list_devices() if (d.vendor, d.product) == (0x045E, 0x0B13) and "Bluetooth" in d.transport
            and (iokit._prop(d.handle, "MaxOutputReportSize") or 0) >= 8]   # the interface that takes the 8-byte report
    if not pads:
        sys.exit("No controller with the Xbox tweak was found over Bluetooth. Is it connected to this Mac, and does the "
                 "terminal have Input Monitoring (System Settings, Privacy & Security)?")
    def send(strong, weak):
        report = bytes([3, a.mask & 0xFF, 0, 0, strong, weak, a.duration, a.delay, a.loops])   # ID 3, then the value
        rc = iokit.iok.IOHIDDeviceSetReport(pads[0].handle, 1, 3, (C.c_uint8 * len(report)).from_buffer_copy(report), len(report))
        if rc:
            sys.exit(f"The report couldn't be sent (IOReturn {rc & 0xFFFFFFFF:#x}).")
        return report[1:].hex(" ")

    sent_hex = send(a.strong, a.weak)
    sent = time.monotonic()
    expect = a.duration * (a.loops + 1) / 100 if a.strong or a.weak else 0
    if a.stop_after is not None:
        time.sleep(max(0, sent + a.stop_after / 1000 - time.monotonic()))
        send(0, 0)
        print(f"Sent {sent_hex}, and the stop {(time.monotonic() - sent) * 1000:.0f} ms later.")
        expect = min(expect, a.stop_after / 1000)
    else:
        print(f"Sent {sent_hex}.")
    print(f"  mask {a.mask & 0xFF:#04x}, strong {a.strong}, weak {a.weak}, duration {a.duration / 100:g} s, "
          f"delay {a.delay * 10} ms, loops {a.loops}")
    print(f"An Xbox controller would vibrate {expect:g} s. Press Enter when it stops.")
    if sys.stdin.isatty():
        try:
            input()
            print(f"{time.monotonic() - sent:.1f} s")
        except (KeyboardInterrupt, EOFError):
            print()


if __name__ == "__main__":
    main()
