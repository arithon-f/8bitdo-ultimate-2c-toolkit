# SPDX-License-Identifier: GPL-3.0-or-later
"""Linux hidraw transport. Uses only the Python standard library."""
from __future__ import annotations

import array
import fcntl
import glob
import os
import select
import struct
import time
from pathlib import Path

from . import DeviceInfo, PermissionDenied

# Linux include/uapi/linux/hidraw.h ioctl definitions.
def _ioc(direction: int, kind: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (kind << 8) | number


_IOC_READ = 2
_HIDRAW_DEVINFO = _ioc(_IOC_READ, ord("H"), 0x03, 8)
_HIDRAW_NAME_LEN = 256
_HIDRAW_NAME = _ioc(_IOC_READ, ord("H"), 0x04, _HIDRAW_NAME_LEN)
_HIDRAW_REPORT_DESC_SIZE = 4096
_HIDRAW_REPORT_DESC_SIZE_IOCTL = _ioc(_IOC_READ, ord("H"), 0x01, 4)
_HIDRAW_REPORT_DESC = _ioc(_IOC_READ, ord("H"), 0x02, 4 + _HIDRAW_REPORT_DESC_SIZE)
_MAX_REPORT = 4096
VENDORS = (0x2DC8, 0x045E)


def _ioctl_bytes(fd: int, request: int, size: int) -> bytes:
    buf = bytearray(size)
    fcntl.ioctl(fd, request, buf, True)
    return bytes(buf)


def _descriptor_usage_page(fd: int) -> int:
    """Return the Usage Page in force at the first top-level Collection."""
    # HIDIOCGRDESC requires the actual descriptor length in the first 4 bytes.
    # Without HIDIOCGRDESCSIZE, Linux returns a zero-length descriptor.
    length = struct.unpack("=I", _ioctl_bytes(fd, _HIDRAW_REPORT_DESC_SIZE_IOCTL, 4))[0]
    if not 0 < length <= _HIDRAW_REPORT_DESC_SIZE:
        raise OSError(f"Invalid HID report descriptor length: {length}")
    buf = bytearray(4 + _HIDRAW_REPORT_DESC_SIZE)
    struct.pack_into("=I", buf, 0, length)
    fcntl.ioctl(fd, _HIDRAW_REPORT_DESC, buf, True)
    size = struct.unpack_from("=I", buf)[0]
    desc = bytes(buf[4:4 + min(size, length)])
    page = 0
    i = 0
    while i < len(desc):
        prefix = desc[i]
        i += 1
        if prefix == 0xFE:  # long item
            if i + 2 > len(desc):
                break
            n = desc[i]
            i += 2 + n
            continue
        n = (prefix & 0x03)
        n = 4 if n == 3 else n
        if i + n > len(desc):
            break
        value = int.from_bytes(desc[i:i+n], "little") if n else 0
        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        i += n
        if item_type == 1 and tag == 0:  # Global: Usage Page
            page = value
        elif item_type == 0 and tag == 10:  # Main: Collection
            return page
    return page


def _sysfs_metadata(path: str, bus: int) -> tuple[str, str, int]:
    node = Path("/sys/class/hidraw") / Path(path).name
    try:
        device = (node / "device").resolve()
    except OSError:
        device = node
    phys = ""
    name = ""
    version = 0
    for parent in (device, *device.parents):
        uevent = parent / "uevent"
        try:
            for line in uevent.read_text(errors="replace").splitlines():
                if line.startswith("HID_PHYS="):
                    phys = line.partition("=")[2]
                elif line.startswith("HID_NAME="):
                    name = line.partition("=")[2]
        except OSError:
            pass
    # USB bcdDevice is exposed by the parent USB device, not the HID interface.
    for parent in (device, *device.parents):
        bcd = parent / "bcdDevice"
        try:
            version = int(bcd.read_text().strip(), 16)
            break
        except (OSError, ValueError):
            continue
    transport = "Bluetooth" if bus == 0x05 or "bluetooth" in (str(device) + " " + phys).lower() else "USB"
    return transport, name, version


def list_devices() -> list[DeviceInfo]:
    found: list[DeviceInfo] = []
    for path in sorted(glob.glob("/dev/hidraw*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        except PermissionError:
            # Keep enumeration useful without permission; opening the selected device gives the actionable error.
            continue
        except OSError:
            continue
        try:
            info = _ioctl_bytes(fd, _HIDRAW_DEVINFO, 8)
            bus, vendor, product = struct.unpack("=IHH", info)
            if vendor not in VENDORS:
                continue
            usage_page = _descriptor_usage_page(fd)
            name_buf = _ioctl_bytes(fd, _HIDRAW_NAME, _HIDRAW_NAME_LEN)
            name = name_buf.split(b"\0", 1)[0].decode(errors="replace")
            transport, sys_name, version = _sysfs_metadata(path, bus)
            found.append(DeviceInfo(vendor=vendor, product=product, usage_page=usage_page,
                                    transport=transport, name=sys_name or name, handle=path, version=version))
        except OSError:
            continue
        finally:
            os.close(fd)
    return found


class HidrawChannel:
    def __init__(self, dev: DeviceInfo, report_id: int):
        self.dev = dev
        self.rid = report_id
        self.fd = -1
        self.fd = os.open(str(dev.handle), os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None) -> bytes | None:
        # Protocol reports are already 64 bytes. HIDRAW includes report IDs in byte zero
        # for numbered reports; bootloader reports have no report ID and remain untouched.
        data = bytes(report)
        if len(data) != 64:
            raise ValueError(f"expected a 64-byte HID report, got {len(data)}")
        try:
            written = os.write(self.fd, data)
        except PermissionError as e:
            raise PermissionDenied(f"Permission denied opening {self.dev.handle}; install the udev rules and reconnect the device.") from e
        except OSError:   # gone or a USB error: no answer, as IOKit gives, so the protocol retries and a write says it was interrupted
            return None
        if written != len(data):
            return None

        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            readable, _, _ = select.select([self.fd], [], [], remaining)
            if not readable:
                return None
            try:
                reply = os.read(self.fd, _MAX_REPORT)
            except BlockingIOError:
                continue
            except OSError as e:
                if e.errno in (11, 4):
                    continue
                return None   # the device went away (EIO, ENODEV) or the transfer failed: no answer
            if not reply:
                continue
            if accept is None or accept(reply):
                return reply

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def open_channel(dev: DeviceInfo, report_id: int) -> HidrawChannel:
    return HidrawChannel(dev, report_id)
