# Ultimate 2 Wireless: Xbox identity with rumble (prototype)

A patch for the 8BitDo Ultimate 2 Wireless, firmware 1.10, that makes the controller present itself over Bluetooth as an Xbox Elite controller. Apple's GameController framework then attaches its Xbox driver, which offers haptics and the battery level. With the original firmware, tvOS and macOS see a generic HID gamepad with neither.

Tested on an Apple TV 4K (3rd generation), tvOS 27.2.1. After pairing, GameController reports the category `Xbox One`, the haptic localities `All, Default, Handles, Left Handle, Right Handle, Left Trigger, Right Trigger, Triggers` and the battery level. Rumble runs through Core Haptics. Every input maps to its Xbox element. macOS has not been tested.

## What changes

The patch changes only the Bluetooth presentation. USB, 2.4 GHz and the firmware's other behaviour are unchanged.

| Edit | Address | Original | Patched |
|---|---|---|---|
| PnP ID | `0x1b54c` | `2dc8:6012` | `045e:0b22`, Xbox Elite V2 |
| HID report map | `0x1b4d8` | 113 bytes: input report 1 of 33 bytes, output report 5 | 98 bytes: input report 1 of 19 bytes, output report 3 |
| Report map length in the GATT table | `0x1b92c` | `0x71` | `0x62` |
| Input report notify | `0xe458` | `notify(0x40, 0x1d, payload, 33)` | jump to the cave |
| Cave | `0x1c780` | zero padding, referenced by nothing | `cave.s`: builds the Xbox report and notifies it with length 19 |
| Rumble callback | `0xd53e` | motors from value bytes 0 and 1 | motors from value bytes 3 and 4, the Xbox LOW and HIGH bytes |
| Output report reference | `0x1c6f0` | `05 02` | `03 02` |
| CRC and start-up sum | `0x1ca60` | | recomputed |

**The input report.** The first 9 bytes of the original report have the same layout as the Ultimate 2C's: hat (0-7, 15 released), LX, LY, RX, RY, RT, LT, then the button bits. The cave writes the 19-byte Xbox Elite report: sticks as 16-bit values, triggers as 10-bit values (`v << 2 | v >> 6`, so 255 gives 1023), the hat as 1-8 with 0 released, and the buttons in the Xbox bit positions.

**The rumble path.** The firmware already drives the motors from its own output report 5, through the callback at `0xd534` and the motor routine at `0x12220`. The patch moves the report to ID 3 and reads the motor bytes where the Xbox packet `[0f LT RT LOW HIGH ff 00 eb]` puts them. The trigger motor bytes are ignored, since the controller has no trigger motors.

**The checks.** The bank carries a Telink CRC at `hsize - 4` and the bootloader's start-up sum at `hsize`, both over the first `hsize - 4` bytes. Both are recomputed.

**Not included.** L4, R4, M1 and M2 are not reported, because the Xbox report has no place GameController reads them from. The motion data and the digital trigger bits are dropped. Home stays with the system on tvOS.

## Use it

Firmware 1.10 is not on the update server that `u2w_backup` downloads from. 8BitDo's Ultimate Software V2 installs it. The patch reads bank A from a backup of the controller, so it needs no firmware download.

1. Make a backup with `python3 -m u2w_backup`. The backup holds the controller's pairings and calibration. Keep it private.
2. Build the image: `python3 -m u2w_xbox.patch BACKUP.bin xbox.bin`. Every original byte is checked before it changes, and the result is checked for stray changes.
3. Build the original bank for restoring: `python3 -m u2w_xbox.patch --stock BACKUP.bin stock.bin`.
4. Check without writing: `python3 -m u2w_xbox.write xbox.bin`.
5. Write: `python3 -m u2w_xbox.write xbox.bin --write --trace sent.txt`. This runs `u2w_backup`'s `restore-original` writer with the image in place of 1.09. Its messages still name 1.09.
6. Forget the controller in the host's Bluetooth settings and pair it again.

To put the original firmware back, write `stock.bin` the same way. If the controller doesn't start, hold LB + RB while plugging in the cable to enter update mode, then run the same command.

## Rebuild the cave

`cave.s` assembles with the Telink tc32 toolchain (flyskywhy/tc32, `macos` branch). Link it at the cave address with the two firmware addresses it calls:

```sh
tc32-elf-as -o cave.o cave.s
tc32-elf-ld -Ttext=0x1c780 --defsym=notify=0x188d0 --defsym=back=0xe464 -o cave.elf cave.o
tc32-elf-objcopy -O binary --only-section=.text cave.elf cave.bin
```

`CAVE` in `patch.py` holds the resulting bytes.
