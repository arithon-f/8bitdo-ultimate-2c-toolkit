#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the dongle's blob from dongle.s: assemble it for ARM Thumb-1 with clang, then convert it to Telink TC32, whose
instructions are Thumb's with the top nibble of each halfword permuted. Writes u2c_customfw/firmware/blobs/dinput.bin.

    python3 firmware-src/dongle.py      (on a Mac, Xcode's clang; elsewhere any clang with the ARM target)
"""
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent / "u2c_customfw" / "firmware" / "blobs" / "dinput.bin"
TC32 = {0x0: 0xF, 0x1: 0xE, 0x2: 0xA, 0x3: 0xB, 0x4: 0x0, 0x5: 0x1, 0x6: 0x5, 0x7: 0x4,
        0x8: 0x2, 0x9: 0x3, 0xA: 0x7, 0xB: 0x6, 0xC: 0xD, 0xD: 0xC, 0xE: 0x8, 0xF: 0x9}   # Thumb's top nibble -> TC32's


def text_and_code_end(obj: bytes) -> tuple[bytes, int]:
    """The .text section of an ELF32 object, and the value of its code_end label."""
    shoff, = struct.unpack_from("<I", obj, 0x20)
    size, num, names = struct.unpack_from("<HHH", obj, 0x2E)
    heads = [struct.unpack_from("<10I", obj, shoff + i * size) for i in range(num)]
    name = lambda tab, off: obj[tab + off:obj.index(b"\0", tab + off)].decode()
    secs = {name(heads[names][4], h[0]): h for h in heads}
    if any(n.startswith(".rel") for n in secs):
        sys.exit("dongle.s left a relocation: every address must be known when it's assembled")
    text, symtab, strtab = secs[".text"], secs[".symtab"], secs[".strtab"]
    for i in range(symtab[5] // 16):
        st_name, value = struct.unpack_from("<II", obj, symtab[4] + 16 * i)
        if name(strtab[4], st_name) == "code_end":
            return obj[text[4]:text[4] + text[5]], value
    sys.exit("dongle.s has no code_end label")


def main():
    clang = ["xcrun", "clang"] if shutil.which("xcrun") else ["clang"]
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "dongle.o"
        subprocess.run([*clang, "-c", "-target", "thumbv4t-none-eabi", str(HERE / "dongle.s"), "-o", str(obj)], check=True)
        text, code_end = text_and_code_end(obj.read_bytes())
    out = bytearray(text)
    for i in range(0, code_end, 2):   # instructions only: the constants after code_end stay as they are
        hw, = struct.unpack_from("<H", out, i)
        struct.pack_into("<H", out, i, TC32[hw >> 12] << 12 | hw & 0xFFF)
    OUT.write_bytes(out)
    print(f"wrote {OUT} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
