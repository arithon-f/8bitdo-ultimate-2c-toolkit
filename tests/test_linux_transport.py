import os
from unittest.mock import patch
from u2c_customfw.transport import libusb


def test_default_output_is_interrupt():
    class Device:
        def __init__(self):
            self.writes = []
        def write(self, ep, data, timeout):
            self.writes.append((ep, bytes(data)))
            return len(data)
        def ctrl_transfer(self, *args, **kwargs):
            raise AssertionError("SET_REPORT should not be default")
    ch = object.__new__(libusb.LibusbChannel)
    ch.device = Device()
    ch.rid = 0x81
    ch._drain = lambda: None
    ch._receive = lambda timeout: bytes([2, 5, 0]) + bytes(61)
    with patch.dict(os.environ, {}, clear=True):
        result = ch.xfer(bytes([0x81, 5, 5]), 0.1)
    assert result[:3] == bytes([2, 5, 0])
    assert ch.device.writes[0][0] == 0x06
    assert len(ch.device.writes[0][1]) == 64


def test_a_usb_error_reads_as_no_answer_so_the_write_is_retried_and_reported_as_interrupted():
    import errno
    from u2c_customfw.transport import hidraw
    ch = object.__new__(hidraw.HidrawChannel)
    ch.fd, ch.rid, ch.dev = 3, 0, None
    with patch("os.write", side_effect=OSError(errno.ENODEV, "No such device")):
        assert ch.xfer(bytes(64)) is None
    with patch("os.write", return_value=64), patch("select.select", return_value=([3], [], [])), \
            patch("os.read", side_effect=OSError(errno.EIO, "Input/output error")):
        assert ch.xfer(bytes(64)) is None


def test_libusb_errors_read_as_no_answer_and_close_quietly():
    class USBError(OSError):
        pass

    class Core:
        pass
    Core.USBError, Core.USBTimeoutError = USBError, type("T", (USBError,), {})

    class Device:
        def write(self, ep, data, timeout):
            raise USBError(19, "No such device")
    ch = object.__new__(libusb.LibusbChannel)
    ch.device, ch.rid, ch.core = Device(), 0x81, Core
    ch._drain = lambda: None
    assert ch.xfer(bytes([0x81]).ljust(64, b"\0")) is None

    class Util:
        disposed = False
        def release_interface(self, dev, intf):
            raise USBError(19, "No such device")
        def dispose_resources(self, dev):
            Util.disposed = True
    ch.claimed, ch.util = True, Util()
    ch.close()
    assert Util.disposed and not ch.claimed


def load_tests(loader, tests, pattern):   # these are plain functions: run them under unittest too
    import unittest
    suite = unittest.TestSuite()
    for name, f in sorted(globals().items()):
        if name.startswith("test_") and callable(f):
            suite.addTest(unittest.FunctionTestCase(f))
    return suite
