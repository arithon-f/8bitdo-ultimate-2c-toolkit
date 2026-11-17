"""Linux USB transport and device routing regression tests."""
from unittest.mock import patch
import pytest
from u2c_customfw.ops import devices
from u2c_customfw.transport import DeviceInfo
from u2c_customfw.transport import linux, libusb

def info(vid, pid, page, handle, version=0):
    return DeviceInfo(vid, pid, page, "USB", "test", handle, version)

def test_stock_and_patched_controller_modes():
    items = [info(0x2DC8, 0x310A, 0xFF7A, "/dev/hidraw0"),
             info(0x045E, 0x028E, 0xFF7A, (1, 2), 0x0114),
             info(0x2DC8, 0x301C, 0xFFA0, "/dev/hidraw1")]
    with patch.object(devices.transport, "list_devices", return_value=items):
        assert [d.mode for d in devices.find()] == ["cable", "cable_360", "dongle"]

def test_paired_receiver_mode():
    with patch.object(devices.transport, "list_devices", return_value=[
        info(0x045E, 0x028E, 0xFF7A, (1, 3), devices.DONGLE_BCD)]):
        assert [d.mode for d in devices.find()] == ["dongle_paired"]

def test_linux_routes_stock_to_hidraw_and_xbox_to_libusb():
    with patch.object(linux.hidraw, "open_channel", return_value="hidraw") as h, \
         patch.object(linux.libusb, "open_channel", return_value="libusb") as u:
        assert linux.open_channel(info(0x2DC8, 0x310A, 0xFF7A, "/dev/hidraw0"), 0x81) == "hidraw"
        assert linux.open_channel(info(0x045E, 0x028E, 0xFF7A, (1, 2)), 0x81) == "libusb"
        h.assert_called_once()
        u.assert_called_once()

def test_libusb_rejects_oversized_or_wrong_report_before_usb_write():
    ch = object.__new__(libusb.LibusbChannel)
    ch.rid = 0x81
    with pytest.raises(ValueError, match="longer than 64"):
        ch.xfer(b"\x81" * 65)
    with pytest.raises(ValueError, match="does not match"):
        ch.xfer(b"\x80\x05")
