import errno
import unittest
from unittest import mock
from u2c_customfw.ops import dongle
from tests.test_dongle import World, STOCK, flash


class DongleTransitionTests(unittest.TestCase):
    def test_eio_on_disconnect_is_not_a_failure_if_bootloader_appears(self):
        world = World(flash(STOCK))
        original_open = world.open

        def open_eio(info, rid):
            ch = original_open(info, rid)
            if world.mode == 'dongle':
                original_xfer = ch.xfer
                def xfer(req, *args, **kwargs):
                    reply = original_xfer(req, *args, **kwargs)
                    if req[:5] == b'\x81\x05\x00\x51\x00':
                        raise OSError(errno.EIO, 'USB disconnected')
                    return reply
                ch.xfer = xfer
            return ch

        msg = dongle.mode_test(world.find, open_eio, wait=0.001)
        self.assertIn('No firmware was erased or written', msg)
        self.assertEqual(world.mode, 'dongle')
        self.assertEqual(bytes(world.flash), flash(STOCK))

    def test_eio_without_bootloader_is_not_treated_as_success(self):
        world = World(flash(STOCK))
        def open_eio(info, rid):
            ch = world.open(info, rid)
            def xfer(req, *args, **kwargs):
                raise OSError(errno.EIO, 'USB disconnected')
            ch.xfer = xfer
            return ch
        with mock.patch.object(dongle, '_wait', return_value=None):
            with self.assertRaisesRegex(dongle.OpError, 'did not appear'):
                dongle.mode_test(world.find, open_eio, wait=0.001)
        self.assertEqual(bytes(world.flash), flash(STOCK))

    def test_other_os_errors_are_not_swallowed(self):
        class Broken:
            def xfer(self, *args, **kwargs):
                raise OSError(errno.EACCES, 'permission denied')
        with self.assertRaises(OSError) as e:
            dongle._request_update_mode(Broken())
        self.assertEqual(e.exception.errno, errno.EACCES)

    def test_unexpected_bootloader_identity_prevents_restart(self):
        world = World(flash(STOCK))
        with mock.patch.object(dongle.boot, 'identify', return_value=dongle.boot.CONTROLLER_ID):
            with self.assertRaisesRegex(dongle.OpError, 'not 0x301c'):
                dongle.mode_test(world.find, world.open, wait=0.001)
        self.assertEqual(world.mode, 'boot')
        self.assertEqual(bytes(world.flash), flash(STOCK))
