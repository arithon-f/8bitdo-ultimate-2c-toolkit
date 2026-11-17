# SPDX-License-Identifier: GPL-3.0-or-later
"""Combine hidraw with libusb for the Xbox-compatible wired interface."""
from . import hidraw, libusb


def list_devices():
    return hidraw.list_devices() + libusb.list_devices()


def open_channel(dev, report_id):
    if isinstance(dev.handle, tuple):
        return libusb.open_channel(dev, report_id)
    return hidraw.open_channel(dev, report_id)
