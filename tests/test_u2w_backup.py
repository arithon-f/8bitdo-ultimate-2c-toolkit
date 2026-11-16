# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import io
import json
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

from u2c_customfw.transport import DeviceInfo
from u2w_backup import __main__ as app, core, sim

U2W = DeviceInfo(0x2DC8, 0x310B, 0xFF7A, "USB", "8BitDo Ultimate 2 Wireless Controller", None, 0x0114)
PAYLOAD = b"\x0e\x80\x6d\x00" + bytes(range(256)) * 0x230 + core.NAME   # stands in for 8BitDo's 1.09


def flash(size=0x80000):
    f = bytearray(sim.image(PAYLOAD))
    return bytes(f[:size]) if size <= len(f) else bytes(f + b"\xff" * (size - len(f)))


class Flaky(sim.Channel):
    """Changes one byte when the second pass starts (address 0 is read once to measure, then once per pass)."""
    reads = 0

    def xfer(self, report, timeout=0.5, accept=None):
        if int.from_bytes(report[14:18], "little") == 0:
            self.reads += 1
            if self.reads == 3:
                self.flash = self.flash[:0x7E000] + b"\x00" + self.flash[0x7E001:]
        return super().xfer(report, timeout, accept)


class ReadTest(unittest.TestCase):
    def test_the_read_request_is_the_ultimate_2cs(self):
        r = core.request(0x12345, 46)
        self.assertEqual(r[0:3], b"\x81\x05\x05")
        self.assertEqual(r[6:8], (46).to_bytes(2, "little"))
        self.assertEqual(r[14:18], (0x12345).to_bytes(4, "little"))
        self.assertEqual(len(r), 64)

    def test_a_reply_for_another_address_is_not_taken(self):
        class Wrong(sim.Channel):
            def xfer(self, report, timeout=0.5, accept=None):
                r = bytearray(super().xfer(report))
                r[14] ^= 1
                return bytes(r)
        self.assertIsNone(core.read(Wrong(flash()), 0x1000, 16))

    def test_flash_size_from_where_it_repeats(self):
        for size in (0x80000, 0x100000):
            self.assertEqual(core.flash_size(sim.Channel(flash(size))), size)


class FindTest(unittest.TestCase):
    def test_only_the_ultimate_2_wireless_by_cable(self):
        self.assertIs(core.find([U2W]), U2W)
        for devices, words in (([], "No controller"),
                               ([DeviceInfo(0x2DC8, 0x310A, 0xFF7A, "USB", "2C", None)], "not an Ultimate 2 Wireless"),
                               ([DeviceInfo(0x2DC8, 0x6012, 0x1, "Bluetooth Low Energy", "", None)], "Bluetooth"),
                               ([U2W, U2W], "More than one")):
            with self.assertRaises(core.Stop) as e:
                core.find(devices)
            self.assertIn(words, str(e.exception))


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        sim.sent.clear()

    def run_app(self, channel):
        out = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(out):
            app.run(lambda: [U2W], lambda d, rid: channel, self.dir, opener=None)
        return out.getvalue()

    def test_whole_run_sends_only_reads_and_shares_none_of_the_units_bytes(self):
        f = flash()
        orig = core.official
        core.official = lambda *a: PAYLOAD
        try:
            out = self.run_app(sim.Channel(f))
        finally:
            core.official = orig
        self.assertTrue(sim.sent)
        self.assertTrue(all(r[0:3] == b"\x81\x05\x05" and len(r) == 64 for r in sim.sent))
        backup = next(self.dir.glob("backup-*.bin"))
        self.assertEqual(backup.read_bytes(), f)
        zpath = next(self.dir.glob("report-*.zip"))
        self.assertIn(f"done {zpath}", out)
        self.assertIn("note Seen: 2dc8:310b, page 0xff7a, USB, version 0114", out)
        z = zipfile.ZipFile(zpath)
        self.assertEqual(z.namelist(), ["report.json"])
        blob = z.read("report.json")
        self.assertNotIn(f[0x7E000:0x7E010].hex(), blob.decode())   # the unit's own data
        self.assertNotIn(f[0x7E000:0x7E010], blob)
        self.assertIn(f"Sent {len(sim.sent)} reports to the controller, all of them reads (81 05 05).", out)
        rep = json.loads(blob)
        self.assertEqual(rep["bootloader_range"], "0x0-0x5000")
        self.assertEqual(rep["bootloader_sha256"], hashlib.sha256(f[:0x5000]).hexdigest())
        self.assertEqual(rep["backup_sha256"], hashlib.sha256(f).hexdigest())
        self.assertEqual(rep["flash_size"], "0x80000")
        self.assertEqual(rep["firmware_version"], 1.09)
        self.assertTrue(rep["same_as_8bitdo_1_09"])
        kinds = {s["address"]: s for s in rep["sectors"]}
        self.assertEqual(kinds["0x5000"]["kind"], "8BitDo firmware 1.09")
        self.assertEqual(kinds["0x7f000"]["kind"], "empty")
        self.assertEqual(kinds["0x7e000"]["kind"], "data")
        self.assertEqual(kinds["0x7e000"]["where"], ["0x7e000-0x7e01f"])

    def test_two_different_reads_save_nothing(self):
        with self.assertRaises(core.Stop) as e:
            self.run_app(Flaky(flash()))
        self.assertIn("differ in 1 place", str(e.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_another_devices_memory_is_not_saved(self):
        f = flash().replace(core.NAME, b"x" * len(core.NAME))
        with self.assertRaises(core.Stop):
            self.run_app(sim.Channel(f))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_only_reads_get_through_and_each_is_traced(self):
        trace = io.StringIO()
        ch = core.ReadsOnly(sim.Channel(flash()), trace)
        self.assertEqual(core.read(ch, 0x5000, 4), b"\x0e\x80\x6d\x00")
        for other in (bytes([0x81, 0x05, 0x00, 0x51, 0x00]).ljust(64, b"\0"), b"\x81\x05\x05", b"\x81\x05\xc1".ljust(64, b"\0")):
            with self.assertRaises(core.Stop):
                ch.xfer(other)
        self.assertEqual(ch.sent, 1)
        self.assertEqual(trace.getvalue(), core.request(0x5000, 4).hex(" ") + "\n")
        self.assertEqual(len(sim.sent), 1)


class OfficialTest(unittest.TestCase):
    def test_only_the_known_file_is_used(self):
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): pass
        listing = json.dumps({"list": [{"filePathName": "/f.dat"}]}).encode()
        def opener(dat):
            return lambda req, timeout=0: R(listing if not isinstance(req, str) else dat)
        self.assertIsNone(core.official(opener(b"not it")))
        dat = bytes(0x1C) + PAYLOAD
        with unittest.mock.patch.object(core, "DAT_SHA256", hashlib.sha256(dat).hexdigest()):
            self.assertEqual(core.official(opener(dat)), PAYLOAD)


class UpdateModeTest(unittest.TestCase):
    """The update-mode check on a simulated controller that restarts into update mode and back."""
    def setUp(self):
        from u2c_customfw.protocol import boot
        from u2w_backup import update_mode
        self.boot, self.um = boot, update_mode
        self.dir = Path(tempfile.mkdtemp())
        self.flash = flash()
        (self.dir / "backup-20261116-000000.bin").write_bytes(self.flash)
        sim.sent.clear()
        sim.state.update(mode="app", flash=self.flash)
        self.addCleanup(lambda: sim.state.update(mode="app", flash=None))
        self.lines = []

    def say(self, *words):
        self.lines.append(" ".join(str(w) for w in words))

    def run_check(self, **kw):
        self.um.check(sim.list_devices, sim.open_channel, self.dir, self.say, wait=2, **kw)

    def app_reports(self):
        return [r for r in sim.sent if r[0] == 0x81]

    def boot_cmds(self):
        return [int.from_bytes(r[1:3], "little") for r in sim.sent if r[0] == 5]

    def test_enters_reads_and_leaves_without_erasing_or_writing(self):
        trace = io.StringIO()
        self.run_check(trace=trace)
        self.assertEqual(self.lines[-1], "done update mode checked")
        self.assertIn("It identifies as 0x6012", "\n".join(self.lines))
        self.assertIn("Bootloader read in update mode matches the backup; firmware matches.", "\n".join(self.lines))
        app = self.app_reports()
        self.assertEqual([r for r in app if r[:3] != b"\x81\x05\x05"], [self.um.ENTER])
        cmds = self.boot_cmds()
        self.assertEqual(set(cmds), {8, 5, 7})
        self.assertEqual((cmds[0], cmds[-1], cmds.count(7)), (8, 7, 1))
        self.assertEqual(sim.state["mode"], "app")
        self.assertEqual(len(trace.getvalue().splitlines()), len(sim.sent))

    def test_another_controller_gets_nothing_but_reads(self):
        (self.dir / "backup-20261116-000000.bin").write_bytes(b"\0" * 0x5000 + self.flash[0x5000:])
        with self.assertRaises(core.Stop) as e:
            self.run_check()
        self.assertIn("isn't the one in your latest backup", str(e.exception))
        self.assertTrue(all(r[:3] == b"\x81\x05\x05" for r in sim.sent))
        self.assertEqual(sim.state["mode"], "app")

    def test_a_bootloader_that_isnt_this_controllers_gets_only_identify(self):
        class Other(sim.Boot):
            def __init__(self, f):
                sim.SimBoot.__init__(self, f, identity=0x301B)
        with unittest.mock.patch.object(sim, "Boot", Other):
            with self.assertRaises(core.Stop) as e:
                self.run_check()
        self.assertIn("0x301b, not 0x6012", str(e.exception))
        self.assertIn("leave-update-mode", str(e.exception))
        self.assertEqual(self.boot_cmds(), [8])

    def test_erase_and_write_are_refused(self):
        ch = self.um.BootReadsOnly(sim.Boot(self.flash))
        for r in (self.boot.request(4, 0x5000, 0x1000), self.boot.request(3, 0x5000, 0, b"x" * 46),
                  self.boot.request(4, 0x0, 0x1000)):
            with self.assertRaises(core.Stop):
                ch.xfer(r)
        self.assertEqual(ch.sent, 0)

    def test_leave_sends_identify_and_restart(self):
        sim.state["mode"] = "boot"
        self.um.leave(sim.list_devices, sim.open_channel, self.say)
        self.assertEqual(self.boot_cmds(), [8, 7])
        self.assertEqual(sim.state["mode"], "app")

    def test_without_a_backup_nothing_is_sent(self):
        for p in self.dir.glob("backup-*.bin"):
            p.unlink()
        with self.assertRaises(core.Stop) as e:
            self.run_check()
        self.assertIn("Make a backup first", str(e.exception))
        self.assertEqual(sim.sent, [])
