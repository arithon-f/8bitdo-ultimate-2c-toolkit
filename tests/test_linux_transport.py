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
