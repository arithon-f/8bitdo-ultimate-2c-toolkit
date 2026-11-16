# SPDX-License-Identifier: GPL-3.0-or-later
"""A simulated Ultimate 2 Wireless for trying the app without one (U2W_SIM=<folder>): a 512 KB flash that answers reads
the way 1.09 does, with 8BitDo's firmware if its server can be reached, and records every report it is sent."""
import random
import time

from u2c_customfw.transport import DeviceInfo

from . import core

SIZE = 0x80000
sent = []


def image(payload: bytes | None) -> bytes:
    rnd = random.Random(1)
    flash = bytearray(b"\xff" * SIZE)
    flash[0:0x4000] = rnd.randbytes(0x4000)                             # the bootloader
    body = payload or (b"\x0e\x80\x6d\x00" + rnd.randbytes(0x23000) + core.NAME)
    flash[core.BASE:core.BASE + len(body)] = body
    flash[0x7E000:0x7E020] = rnd.randbytes(0x20)                         # the unit's own data
    return bytes(flash)


class Channel:
    def __init__(self, flash: bytes, delay: float = 0.0):
        self.flash, self.delay = flash, delay

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        sent.append(bytes(report))
        if report[0:3] != b"\x81\x05\x05":
            return None
        n, addr = int.from_bytes(report[6:8], "little"), int.from_bytes(report[14:18], "little")
        time.sleep(self.delay)
        data = bytes(self.flash[(addr + i) % len(self.flash)] for i in range(min(n, 46)))
        return b"\x02\x05\x00\x00\x05\x00" + report[6:8] + bytes(6) + report[14:18] + data

    def close(self):
        pass


def list_devices():
    return [DeviceInfo(core.VENDOR, 0x310B, core.PAGE, "USB", "8BitDo Ultimate 2 Wireless Controller", None, 0x0114)]


def open_channel(dev, report_id):
    return Channel(image(core.official()), delay=0.0004)
