# SPDX-License-Identifier: GPL-3.0-or-later
"""Put 8BitDo's firmware 1.09 back on bank A (0x5000-0x28800). Without --write it only checks and says what it would do.

Read-only first: the latest backup, 8BitDo's 1.09 from its server (checked by SHA-256), the bootloader by cable or in
update mode (it must match the backup), no update staged in the record at 0x31000, and identify 0x6012 in update mode.

Then, sector by sector: erase 4 KB, write it in 46-byte chunks (the bootloader checks each chunk's CRC), read it back.
Sector 0x5000, which holds the header the bootloader checks bank A against (length at 0x5018), goes last, so the header
already in place stays valid until then. Nothing outside 0x5000-0x29000 is erased or written: BootWriter refuses it.
If anything stops, the controller stays in update mode (the flag survives unplugging) and this can be run again.
"""
import time

from u2c_customfw.protocol import boot

from . import core, update_mode as um

SIZE = 0x23800                       # 8BitDo's 1.09 payload
END = core.BASE + SIZE               # 0x28800
ERASE_END = 0x29000
SECTOR = 0x1000
RECORD = 0x31000
STAGED_MAGIC = (0xAEB14D6C).to_bytes(4, "little")
ORDER = list(range(core.BASE + SECTOR, ERASE_END, SECTOR)) + [core.BASE]
STOPPED = ("The controller's firmware is half-written, and the controller is still in update mode. Run "
           "`python3 -m u2w_backup restore-original --write` again to finish. Until then, don't hold Home, unplug it or "
           "run leave-update-mode: restarting with half-written firmware is the one thing to avoid. (On the Ultimate 2C "
           "the update-mode flag survives unplugging; that hasn't been seen on this controller yet.)")


class BootWriter(um.BootReadsOnly):
    """Identify, read, restart, and erase (one aligned 4 KB sector) and write (46 bytes) only inside 0x5000-0x29000."""
    ALLOWED = (8, 5, 7, 4, 3)

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        cmd, addr = int.from_bytes(report[1:3], "little"), int.from_bytes(report[13:17], "little")
        n = int.from_bytes(report[5:7], "little") if cmd == 3 else int.from_bytes(report[9:13], "little")
        if cmd == 4 and not (addr % SECTOR == 0 and n == SECTOR and core.BASE <= addr < ERASE_END):
            raise core.Stop(f"Refused to erase {n:#x} bytes at {addr:#x}. " + STOPPED)
        if cmd == 3 and not (core.BASE <= addr and addr + n <= END and 0 < n <= boot.CHUNK):
            raise core.Stop(f"Refused to write {n} bytes at {addr:#x}. " + STOPPED)
        if len(report) != 64 or report[0] != 5 or cmd not in self.ALLOWED:
            raise core.Stop(f"Refused to send {report[:8].hex(' ')}. " + STOPPED)
        self.sent += 1
        if self.trace:
            self.trace.write(report.hex(" ") + "\n")
        return self.ch.xfer(report, timeout, accept)


def staged(record: bytes) -> bool:
    """The bootloader's own test (0xc0c): the magic at +0x18 and a length of 1 to 0x3efff at +0x20."""
    return record[0x18:0x1C] == STAGED_MAGIC and 1 <= int.from_bytes(record[0x20:0x24], "little") <= 0x3EFFF


def describe(record: bytes) -> str:
    """The fields the bootloader reads (0xae8, 0xc0c, 0xb5c): version, staged-update magic, source and length."""
    v = record[0x0C]
    return (f"version {v / 100:.2f}, " if v not in (0, 0xFF) else "no version, ") + \
        f"magic {record[0x18:0x1C][::-1].hex()}, source {int.from_bytes(record[0x1C:0x20], 'little'):#x}, " \
        f"length {int.from_bytes(record[0x20:0x24], 'little'):#x}"


def _write_sector(ch, a: int, payload: bytes) -> bool:
    want = payload[a - core.BASE:a - core.BASE + SECTOR]
    boot.erase(ch, a, SECTOR)
    for c in range(a, a + len(want), boot.CHUNK):
        blk = want[c - a:c - a + boot.CHUNK]
        if blk != b"\xff" * len(blk):
            boot.write_chunk(ch, c, SIZE, blk)
    return boot.read(ch, a, SECTOR) == (want + b"\xff" * SECTOR)[:SECTOR]


def run(devices, open_channel, folder, say, write=False, trace=None, opener=None, wait: float = 30.0) -> None:
    backup = um.latest_backup(folder)
    payload = core.official(opener) if opener else core.official()
    if payload is None or len(payload) != SIZE:
        raise core.Stop("8BitDo's firmware 1.09 couldn't be downloaded from its server and checked, so nothing was done.")
    same_now = backup[core.BASE:END] == payload
    say("status", "Downloaded 8BitDo's firmware 1.09 and checked its SHA-256. Your backup's firmware "
                  + ("is the same one." if same_now else "is NOT the same, so this puts 1.09 back."))
    bdev = next((d for d in devices() if um._in_boot(d)), None)
    if bdev is None:
        dev = core.find(devices())
        ch = um.EnterOnce(open_channel(dev, 0x81), trace)
        try:
            if core.read_range(ch, 0, core.BASE) != backup[:core.BASE]:
                raise core.Stop("This controller's bootloader isn't the one in your latest backup, so nothing was sent.")
            record = core.read_range(ch, RECORD, 0x34)
            say("status", "Update record at 0x31000: " + describe(record))
            if staged(record):
                raise core.Stop("A firmware update is staged on this controller, and its bootloader would install it over "
                                "this at the next start. Nothing was written.")
            if not write:
                say("status", f"Check passed: it would erase and rewrite bank A ({len(ORDER)} sectors, "
                              "0x5000-0x29000) in update mode, sector 0x5000 last. Nothing was sent but reads.")
                say("done", "checked")
                return
            say("status", "Restarting into update mode (81 05 00 51 00).")
            ch.xfer(um.ENTER, 0.3)
        finally:
            ch.close()
        bdev = um._wait(devices, um._in_boot, wait)
        if bdev is None:
            raise core.Stop("The controller didn't show up in update mode within 30 seconds. If macOS asked whether to "
                            "allow the accessory, allow it and run this again. " + um.LEAVE_HELP)
    else:
        say("status", "The controller is already in update mode.")
    bch = BootWriter(open_channel(bdev, 0), trace)
    try:
        who = boot.identify(bch)
        if who != um.IDENTITY:
            raise core.Stop(f"The device in update mode identifies as {who if who is None else hex(who)}, not 0x6012, "
                            "so nothing else was sent to it.")
        if boot.read(bch, 0, core.BASE) != backup[:core.BASE]:
            raise core.Stop("The bootloader read in update mode isn't the one in your latest backup. Nothing was written. "
                            + um.LEAVE_HELP)
        if staged(boot.read(bch, RECORD, 0x24)):
            raise core.Stop("A firmware update is staged on this controller. Nothing was written. " + um.LEAVE_HELP)
        if not write:
            say("status", f"Check passed in update mode: it would rewrite bank A ({len(ORDER)} sectors). Nothing was written.")
            say("done", "checked")
            return
        say("status", f"Rewriting bank A one 4 KB sector at a time ({len(ORDER)} sectors), sector 0x5000 last. "
                      "Keep the cable connected.")
        t0 = time.monotonic()
        for i, a in enumerate(ORDER):
            if not _write_sector(bch, a, payload) and not _write_sector(bch, a, payload):
                raise core.Stop(f"Sector {a:#x} didn't read back as written, twice. " + STOPPED)
            say("progress", i + 1, len(ORDER))
        if boot.read(bch, core.BASE, SIZE) != payload:
            raise core.Stop("Bank A doesn't read back as 8BitDo's 1.09. " + STOPPED)
        say("status", f"Written and read back in {time.monotonic() - t0:.0f} s. Restarting (bootloader command 7).")
        bch.xfer(boot.request(7), 0.5)
    except core.Stop:
        raise
    except Exception as e:  # noqa: BLE001 - say how to finish
        raise core.Stop(f"{e}. " + STOPPED) from e
    finally:
        bch.close()
    t1 = time.monotonic()
    back = um._wait(devices, lambda d: d.vendor == core.VENDOR and d.product in core.PRODUCTS and d.usage_page == core.PAGE, wait)
    if back is None:
        raise core.Stop("The controller didn't come back within 30 seconds. Hold LB + RB while plugging it in to put it "
                        "in update mode, then run this again.")
    ch = core.ReadsOnly(open_channel(back, 0x81), trace)
    try:
        ok = core.read_range(ch, core.BASE, SIZE) == payload
    finally:
        ch.close()
    say("status", f"Back after {time.monotonic() - t1:.1f} s as {back.vendor:04x}:{back.product:04x}; by cable its "
                  f"firmware {'reads as' if ok else 'does NOT read as'} 8BitDo's 1.09. Sent {bch.sent} reports in update mode.")
    if not ok:
        raise core.Stop("Please paste this output in the issue.")
    say("done", "8BitDo's firmware 1.09 restored")
