# Ultimate 2 Wireless: Xbox identity with rumble (prototype)

A patch for the 8BitDo Ultimate 2 Wireless, firmware 1.10, that makes the controller present itself over Bluetooth as an Xbox Elite controller. Apple's GameController framework then attaches its Xbox driver, which offers haptics and the battery level. With the original firmware, tvOS and macOS see a generic HID gamepad with neither.

Tested on an Apple TV 4K (3rd generation), tvOS 27.2.1. After pairing, GameController reports the category `Xbox One`, the haptic localities `All, Default, Handles, Left Handle, Right Handle, Left Trigger, Right Trigger, Triggers` and the battery level. Rumble runs through Core Haptics. Every input maps to its Xbox element. macOS has not been tested.

| Procedure | Tested on hardware |
|---|---|
| Back up, build, write the patched image | Yes |
| Write the controller's own original bank back | Yes |
| Return to 8BitDo's 1.09 from its server (`restore-original --write`) | The same writer is tested. The 1.09 download path has not been run on a patched controller. |
| Return to stock with 8BitDo's own software | No |

## Requirements

- A Mac with Python 3.12 or later. Run every command from the root of this repository.
- Input Monitoring permission for the terminal app: System Settings › Privacy & Security › Input Monitoring. After adding it, quit and reopen the terminal.
- A USB data cable. Unplug the 2.4 GHz adapter from every computer.
- Firmware 1.10 on the controller. 8BitDo's Ultimate Software V2 installs it. The patch checks every byte it changes against 1.10 and refuses any other version.

## Flash a controller

Each controller needs its own backup. The backup holds the controller's Bluetooth pairings and calibration, so keep it private.

1. Update the controller to 1.10 with 8BitDo's Ultimate Software V2.
2. Turn the controller off and connect it to the Mac with the cable.
3. Back up the whole flash. It reads only.

   ```sh
   python3 -m u2w_backup --trace sent.txt
   ```

   The backup and a report go to `~/Documents/Ultimate 2 Wireless Backup/`. In the report, `firmware_version` must be `1.1`.
4. Build the patched image from that backup:

   ```sh
   python3 -m u2w_xbox.patch ~/Documents/"Ultimate 2 Wireless Backup"/backup-<date>.bin xbox.bin
   ```

   If the backup isn't an original 1.10, this stops with "Nothing written" and names the first address that differs.
5. Check without writing. This reads only.

   ```sh
   python3 -m u2w_xbox.write xbox.bin
   ```

   Expected: `Check passed: it would rewrite bank A (36 sectors, 0x5000-0x29000) ...`.
6. Write. Keep the cable connected. It takes about 1 minute.

   ```sh
   python3 -m u2w_xbox.write xbox.bin --write --trace sent.txt
   ```

   Expected, at the end: `Back after ... s as 2dc8:310b; by cable its firmware reads as ...` and `done`. The messages name 1.09 because that wording is part of `u2w_backup`'s writer. The bytes written are `xbox.bin`'s.
7. Unplug the cable and set the mode switch to BT.
8. On every device the controller was paired with, forget it in the Bluetooth settings. A device that keeps the old pairing can keep the old description of the controller.
9. Hold Pair for 3 seconds and pair the controller again. The name is unchanged.
10. Check the result in `tvos/rumble-test` on an Apple TV, or in the controller test app on a Mac (`macos/u2w/build-test.sh`). The category must be `Xbox One` and the haptic localities must be listed.

## Return to stock firmware

This puts 8BitDo's firmware back, downloaded from 8BitDo's update server and checked by SHA-256. The server offers 1.09 for this controller. It needs the backup made in step 3 of "Flash a controller", because the writer compares the bootloader with it.

1. Connect the controller to the Mac with the cable. The controller can be on or off.
2. Check without writing:

   ```sh
   python3 -m u2w_backup restore-original
   ```

3. Write. Keep the cable connected.

   ```sh
   python3 -m u2w_backup restore-original --write --trace sent.txt
   ```

   Expected, at the end: `done 8BitDo's firmware 1.09 restored`.
4. To get 1.10 again, update with 8BitDo's Ultimate Software V2.
5. Forget the controller on every device it was paired with, and pair it again.

### When the controller doesn't start or doesn't answer by cable

1. Turn the controller fully off: unplug the cable, then hold Home for about 12 seconds.
2. Hold LB + RB while plugging the cable in. The controller enters update mode and appears as `2dc8:3208`, "8BitDo Boot". Update mode is part of the bootloader, which no command here writes.
3. Run step 3 of "Return to stock firmware". The writer finds the controller in update mode and writes from there.

To leave update mode without writing, run `python3 -m u2w_backup leave-update-mode`, or hold Home for about 12 seconds with the cable unplugged. `leave-update-mode` restarts the controller only when bank A holds a whole firmware.

### The controller's own original bank

The original 1.10 bank from the backup can also go back, with the same writer:

```sh
python3 -m u2w_xbox.patch --stock ~/Documents/"Ultimate 2 Wireless Backup"/backup-<date>.bin stock.bin
python3 -m u2w_xbox.write stock.bin --write --trace sent.txt
```

## What the patch changes

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

**The checks.** The bank carries a Telink CRC at `hsize - 4` and the bootloader's start-up sum at `hsize`, both over the first `hsize - 4` bytes. Both are recomputed. The bootloader runs bank A only when the sum matches. According to the bootloader code, a failed sum makes it copy bank B, the second firmware copy at `0x32000`, back over bank A. That copy has not been observed.

**Not included.** L4, R4, M1 and M2 are not reported, because the Xbox report has no place GameController reads them from. The motion data and the digital trigger bits are dropped. Home stays with the system on tvOS.

## Rebuild the cave

`cave.s` assembles with the Telink tc32 toolchain (flyskywhy/tc32, `macos` branch, x86_64 binaries that run under Rosetta). Link it at the cave address with the two firmware addresses it calls:

```sh
tc32-elf-as -o cave.o cave.s
tc32-elf-ld -Ttext=0x1c780 --defsym=notify=0x188d0 --defsym=back=0xe464 -o cave.elf cave.o
tc32-elf-objcopy -O binary --only-section=.text cave.elf cave.bin
```

`CAVE` in `patch.py` holds the resulting bytes. After any change, disassemble the patched bank with `tc32-elf-objdump -D -b binary -m tc32 --adjust-vma=0x5000` and check that every branch lands where intended.
