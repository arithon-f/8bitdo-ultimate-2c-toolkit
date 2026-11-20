# SPDX-License-Identifier: GPL-3.0-or-later
"""Linux USB transport for the Xbox-compatible controller's vendor HID interface.

Only interface 2 is claimed. Interface 0 remains owned by xpad.
"""
from __future__ import annotations

import time
import os
import logging

LOG = logging.getLogger(__name__)

from . import DeviceInfo, PermissionDenied

VID, PID = 0x045E, 0x028E
INTERFACE = 2
IN_EP = 0x83
OUT_EP = 0x06
OUT_REPORT = 0x81


def _usb():
    try:
        import usb.core
        import usb.util
    except ImportError as exc:
        raise RuntimeError("PyUSB is required for Xbox-compatible USB controller support: python -m pip install pyusb") from exc
    return usb.core, usb.util


def _interface(device):
    try:
        return device.get_active_configuration()[(INTERFACE, 0)]
    except (KeyError, ValueError):
        return None


def list_devices():
    core, util = _usb()
    found = []
    for dev in core.find(find_all=True, idVendor=VID, idProduct=PID) or ():
        try:
            interface = _interface(dev)
            if interface is None or interface.bInterfaceClass != 3:
                continue
            # Read the HID report descriptor from interface 2 without claiming it.
            descriptor = bytes(dev.ctrl_transfer(0x81, 0x06, 0x2200, INTERFACE, 256, timeout=1000))
            if not descriptor.startswith(bytes.fromhex("06 7a ff 09 01 a1")):
                continue
            name = "Xbox-compatible 8BitDo Ultimate 2C (USB)"
            found.append(DeviceInfo(VID, PID, 0xFF7A, "USB", name,
                                    (dev.bus, dev.address), int(dev.bcdDevice)))
        except core.USBError as exc:
            if getattr(exc, "errno", None) == 13:
                raise PermissionDenied("USB access denied; install the udev rules and reconnect the controller") from exc
            continue
    return found


class LibusbChannel:
    def __init__(self, info, report_id):
        core, util = _usb()
        self.core, self.util = core, util
        self.device = next((d for d in core.find(find_all=True, idVendor=VID, idProduct=PID) or ()
                            if (d.bus, d.address) == info.handle), None)
        if self.device is None:
            raise OSError("Controller disconnected")
        self.claimed = False
        try:
            # No kernel driver is expected on interface 2; never detach xpad on interface 0.
            if self.device.is_kernel_driver_active(INTERFACE):
                raise OSError("The kernel driver owns USB interface 2, and this application will not detach it.")
            util.claim_interface(self.device, INTERFACE)
            self.claimed = True
        except core.USBError as exc:
            if getattr(exc, "errno", None) == 13:
                raise PermissionDenied("Permission denied opening USB interface 2; install udev rules") from exc
            raise
        self.rid = report_id

    def _receive(self, timeout_ms):
        try:
            packet = bytes(self.device.read(IN_EP, 64, timeout=timeout_ms))
        except self.core.USBTimeoutError:
            return None
        # Interrupt IN includes report ID 0x02. Do not fabricate it if absent.
        LOG.debug("libusb IN len=%d prefix=%s", len(packet), packet[:18].hex(" "))
        return packet

    def _drain(self):
        # Unlike macOS run-loop callbacks, Linux may have queued an earlier response.
        # Bound the work; never block waiting for an unsolicited report.
        for _ in range(8):
            if self._receive(2) is None:
                break

    def xfer(self, report: bytes, timeout: float = 0.5, accept=None):
        if len(report) > 64:
            raise ValueError("HID report longer than 64 bytes")
        data = bytes(report).ljust(64, b"\0")
        if self.rid and data[0] != self.rid:
            raise ValueError("Output report ID does not match channel")
        self._drain()
        # Verified on Ultimate 2C Wireless: interrupt OUT endpoint 0x06.
        # Keep SET_REPORT available as a diagnostic override only.
        mode = os.environ.get("U2C_USB_OUTPUT", "interrupt")
        LOG.debug("libusb OUT mode=%s report_id=%#04x prefix=%s", mode, self.rid, data[:18].hex(" "))
        try:
            if mode == "control":
                sent = self.device.ctrl_transfer(0x21, 0x09, 0x0200 | self.rid,
                                                 INTERFACE, data, timeout=max(100, int(timeout * 1000)))
            elif mode == "interrupt":
                sent = self.device.write(OUT_EP, data, timeout=max(100, int(timeout * 1000)))
            else:
                raise ValueError("U2C_USB_OUTPUT must be 'control' or 'interrupt'")
        except self.core.USBError as exc:   # gone or a USB error: no answer, as IOKit gives, so the protocol retries
            LOG.debug("libusb OUT error: %s", exc)
            return None
        LOG.debug("libusb OUT sent=%d", sent)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            try:
                response = self._receive(remaining)
            except self.core.USBError as exc:
                LOG.debug("libusb IN error: %s", exc)
                return None
            if response is None:
                return None
            if response and (accept is None or accept(response)):
                return response
            if response:
                LOG.debug("libusb IN rejected by protocol predicate")
        return None

    def close(self):
        if self.claimed:   # a device that has gone can't release its interface; the handle is freed all the same
            self.claimed = False
            try:
                self.util.release_interface(self.device, INTERFACE)
            except Exception as exc:
                LOG.debug("libusb release error: %s", exc)
            self.util.dispose_resources(self.device)


def open_channel(info, report_id):
    return LibusbChannel(info, report_id)
