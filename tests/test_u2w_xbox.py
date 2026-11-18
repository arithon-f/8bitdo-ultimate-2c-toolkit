# SPDX-License-Identifier: GPL-3.0-or-later
import struct
import unittest

from u2w_xbox import patch


def bank_with_originals() -> bytearray:
    """A stand-in bank A: 1.10's header fields, its original bytes at every edit site, and both checks valid."""
    bank = bytearray(patch.BANK_END - patch.BANK_A)
    bank[patch.DATA_END - patch.BANK_A:] = b"\xff" * (patch.BANK_END - patch.DATA_END)
    struct.pack_into("<H", bank, 2, 110)
    bank[8:12] = b"KNLT"
    struct.pack_into("<I", bank, patch.HSIZE_AT, 0x17A64)
    for addr, old, _ in (patch.PNP, patch.HOOK, patch.RUMBLE, patch.OUT_REF,
                         (patch.MAP_ADDR, patch.STOCK_MAP, ""), (patch.MAP_LEN_AT, "71 00 00 00", "")):
        b = bytes.fromhex(old)
        bank[addr - patch.BANK_A:addr - patch.BANK_A + len(b)] = b
    h, crc, total = patch.checks(bank)
    struct.pack_into("<II", bank, h - 4, crc, total)
    return bank


def flash(bank: bytes) -> bytes:
    return b"\xff" * patch.BANK_A + bytes(bank)


class Patch(unittest.TestCase):
    def test_patched_bank_passes_both_checks_and_changes_only_the_edits(self):
        original = bank_with_originals()
        out = patch.patch(flash(original))
        patch.verify(bytes(original), out)
        o = patch.PNP[0] - patch.BANK_A
        self.assertEqual(out[o:o + 7], bytes.fromhex(patch.PNP[2]))
        self.assertEqual(struct.unpack_from("<I", out, patch.MAP_LEN_AT - patch.BANK_A)[0], 98)
        r = patch.RUMBLE_ADDR - patch.BANK_A
        self.assertEqual(out[r:r + len(patch.RUMBLE_ROUTINE) // 2], bytes.fromhex(patch.RUMBLE_ROUTINE))

    def test_rumble_strength_reaches_255(self):
        # rumble.s: max(handle, trigger) * 164 >> 6, capped at 255. Xbox strengths run 0-100.
        scale = lambda v: min(v * 164 >> 6, 255)
        self.assertEqual([scale(v) for v in (0, 50, 100, 255)], [0, 128, 255, 255])

    def test_refuses_a_bank_that_differs_at_an_edit_site(self):
        bank = bank_with_originals()
        bank[patch.HOOK[0] - patch.BANK_A] ^= 1
        h, crc, total = patch.checks(bank)
        struct.pack_into("<II", bank, h - 4, crc, total)
        with self.assertRaises(patch.NotStock):
            patch.patch(flash(bank))

    def test_refuses_a_bank_that_fails_its_checks(self):
        bank = bank_with_originals()
        bank[0x100] ^= 1
        with self.assertRaises(patch.NotStock):
            patch.stock(flash(bank))


if __name__ == "__main__":
    unittest.main()
