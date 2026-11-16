# Ultimate 2 Wireless Backup (prototype)

A read-only backup of the 8BitDo Ultimate 2 Wireless (firmware 1.09) by USB cable, for [issue #8](https://github.com/carlosbrownef-source/8bitdo-ultimate-2c-toolkit/issues/8). It isn't part of the toolkit's releases.

## Run it from source

You need Python 3.12 or later, and no other package.

```sh
git clone -b u2w-backup https://github.com/carlosbrownef-source/8bitdo-ultimate-2c-toolkit.git
cd 8bitdo-ultimate-2c-toolkit
python3 -m u2w_backup --trace sent.txt
```

macOS only lets an app open the controller's update channel if it has Input Monitoring permission. If the tool says access was refused, add your terminal app in System Settings › Privacy & Security › Input Monitoring, then quit and reopen the terminal.

Before running it, turn the controller off, unplug its 2.4 GHz adapter and connect the controller with a USB cable. The tool prints one line per step and saves its files in Documents › Ultimate 2 Wireless Backup.

## Checking what it sends

- Everything the tool sends to the controller goes through `ReadsOnly` in `u2w_backup/core.py`. It refuses any report that isn't a 64-byte `81 05 05` read and counts the ones it sends. At the end, the tool prints how many reports it sent.
- `--trace FILE` writes every report sent, in hex, one per line. `grep -vc '^81 05 05' sent.txt` prints 0 when all of them were reads.
- From the toolkit it uses only the macOS transport, `u2c_customfw/transport/iokit.py`. There, the only call that sends anything to a device is `IOHIDDeviceSetReport`, in `xfer`.
- In firmware 1.09, the `81 05` reports go to a dispatcher at `0x10b68`. Its read handler, `0x107f8`, reads at most 46 bytes at the address asked and replies; it changes nothing.

## What the files are

- `backup-….bin` is the whole flash, read twice and saved only if both reads match. It holds your controller's own data, such as its Bluetooth pairings, so keep it to yourself.
- `report-….zip` holds only `report.json`, which contains no byte read from the controller. It says which 4 KB sectors match 8BitDo's firmware 1.09 (downloaded from 8BitDo's update server to compare), which are empty and where the others have data. Each data sector also has a hash keyed with `.report-key`, which stays on your Mac. You can check the report against your backup:
  - `shasum -a 256 backup-….bin` gives `backup_sha256`.
  - `head -c 20480 backup-….bin | shasum -a 256` gives `bootloader_sha256` (the bootloader is `0x0`–`0x5000`).

## The app

`macos/u2w/build.sh [arm64|x86_64]` builds the app around the same code: one window that runs `python3 -m u2w_backup` and shows its lines. `U2W_SIM=<folder> python3 -m u2w_backup` runs it against a simulated controller.
