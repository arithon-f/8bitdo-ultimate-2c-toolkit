# SPDX-License-Identifier: GPL-3.0-or-later
"""The battery log that firmware installed with Processor rest keeps since 1.1 (battery_log, firmware-src/rest.c): once a
minute on battery, an 8-byte record appended at 0x53000-0x73000, which flash keeps through power-offs. Read by cable."""
import struct

from ..firmware import image
from . import probe

START, END = 0x53000, 0x73000
CSV_HEADER = "power_on,minute,mv,percent,connected,rumble,interval_ms\n"


def parse(data: bytes) -> list[tuple]:
    """Records up to the first blank one: power-on number, minutes since that power-on, battery mV, the firmware's
    percentage, connected over Bluetooth, a rumble running, and the connection interval in ms."""
    rows = []
    for a in range(0, len(data) - 7, 8):
        r = data[a:a + 8]
        if r[:4] == b"\xff" * 4:
            break
        boot, code, minute, mv, pct, flags = struct.unpack("<BBHHBB", r)
        rows.append((boot, minute, mv, pct, flags >> 1 & 1, flags >> 2 & 1, round(code * 64 / 1000, 2)))
    return rows


def read(ch, mode: str) -> list[tuple]:
    """By cable: a sector at a time, up to the sector where the log ends."""
    out = bytearray()
    for a in range(START, END, image.SECTOR):
        chunk = probe._read(ch, mode, a, image.SECTOR)
        out += chunk
        if any(chunk[i:i + 4] == b"\xff" * 4 for i in range(0, image.SECTOR, 8)):
            break
    return parse(bytes(out))


def csv(rows: list[tuple]) -> str:
    return CSV_HEADER + "".join(",".join(str(v) for v in r) + "\n" for r in rows)


def summary(rows: list[tuple]) -> str:
    """In words: how much it holds."""
    hours = len(rows) / 60
    starts = len({r[0] for r in rows}) if rows else 0
    return (f"{hours:.1f} hours on battery from {starts} power-on{'s' if starts != 1 else ''}, "
            f"from {rows[0][2]} mV to {rows[-1][2]} mV")
