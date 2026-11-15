#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Long rumble over Bluetooth from longrumble.s: assemble it for ARM Thumb-1 with clang, convert it to Telink TC32,
and encode the two calls into it that replace instructions in
motor_set, and the write callback pointer. Writes u2c_customfw/firmware/blobs/longrumble.bin, lrhooka.bin, lrhookb.bin
and lrwrite.bin.

    python3 firmware-src/longrumble.py      (on a Mac, Xcode's clang; elsewhere any clang with the ARM target)
"""
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
BLOBS = HERE.parent / "u2c_customfw" / "firmware" / "blobs"
CODE_AT, CODE_END = 0x1734C, 0x173C0        # the stock Report Map, unused once bt_xbox points the attribute elsewhere
HOOKS = {"lrhooka.bin": (0xFA72, "long_hold"), "lrhookb.bin": (0xFA88, "rearm")}
TC32 = {0x0: 0xF, 0x1: 0xE, 0x2: 0xA, 0x3: 0xB, 0x4: 0x0, 0x5: 0x1, 0x6: 0x5, 0x7: 0x4,
        0x8: 0x2, 0x9: 0x3, 0xA: 0x7, 0xB: 0x6, 0xC: 0xD, 0xD: 0xC, 0xE: 0x8, 0xF: 0x9}   # Thumb's top nibble -> TC32's


def text_and_symbols(obj: bytes) -> tuple[bytes, dict[str, int]]:
    """The .text section of an ELF32 object, and its labels."""
    shoff, = struct.unpack_from("<I", obj, 0x20)
    size, num, names = struct.unpack_from("<HHH", obj, 0x2E)
    heads = [struct.unpack_from("<10I", obj, shoff + i * size) for i in range(num)]
    name = lambda tab, off: obj[tab + off:obj.index(b"\0", tab + off)].decode()
    secs = {name(heads[names][4], h[0]): h for h in heads}
    if any(n.startswith(".rel") for n in secs):
        sys.exit("longrumble.s left a relocation: every address must be known when it's assembled")
    text, symtab, strtab = secs[".text"], secs[".symtab"], secs[".strtab"]
    syms = {}
    for i in range(symtab[5] // 16):
        st_name, value = struct.unpack_from("<II", obj, symtab[4] + 16 * i)
        if st_name:
            syms[name(strtab[4], st_name)] = value & ~1
    return obj[text[4]:text[4] + text[5]], syms


def tc32_call(at: int, to: int) -> bytes:
    """TC32's tjl (Thumb's bl, top nibbles F -> 9) at `at` to `to`."""
    off = to - (at + 4)
    if not -(1 << 22) <= off < 1 << 22 or off & 1:
        sys.exit(f"call {at:#x} -> {to:#x} out of reach")
    return struct.pack("<HH", 0x9000 | (off >> 12) & 0x7FF, 0x9800 | (off >> 1) & 0x7FF)


def main():
    clang = ["xcrun", "clang"] if shutil.which("xcrun") else ["clang"]
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "longrumble.o"
        subprocess.run([*clang, "-c", "-target", "thumbv4t-none-eabi", str(HERE / "longrumble.s"), "-o", str(obj)], check=True)
        text, syms = text_and_symbols(obj.read_bytes())
    code_end = syms["code_end"]
    if syms["long_hold"] != 0 or len(text) > CODE_END - CODE_AT:
        sys.exit("longrumble.s must start with long_hold and fit the stock Report Map's 116 bytes")
    out = bytearray(text)
    for i in range(0, code_end, 2):   # instructions only: the constants after code_end stay as they are
        hw, = struct.unpack_from("<H", out, i)
        if hw >> 12 in (0x9, 0xA, 0xC):   # sp-relative loads, add to pc/sp, ldm/stm: none expected here
            sys.exit(f"longrumble.s +{i:#x}: {hw:04x} is an instruction class this code shouldn't need")
        struct.pack_into("<H", out, i, TC32[hw >> 12] << 12 | hw & 0xFFF)
    (BLOBS / "longrumble.bin").write_bytes(out)
    print(f"wrote {BLOBS / 'longrumble.bin'} ({len(out)} bytes)")
    for blob, (at, label) in HOOKS.items():
        (BLOBS / blob).write_bytes(tc32_call(at, CODE_AT + syms[label]))
        print(f"wrote {BLOBS / blob}: tjl {at:#x} -> {CODE_AT + syms[label]:#x} ({label})")
    (BLOBS / "lrwrite.bin").write_bytes(struct.pack("<I", CODE_AT + syms["long_write"] | 1))   # Thumb-style odd, as bt_xbox's
    print(f"wrote {BLOBS / 'lrwrite.bin'}: the write callback -> {CODE_AT + syms['long_write']:#x} (long_write)")


if __name__ == "__main__":
    main()
