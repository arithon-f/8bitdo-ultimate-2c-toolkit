# Ultimate 2 Wireless: Xbox identity with rumble (prototype)

`u2w_xbox` patches firmware 1.10 of the 8BitDo Ultimate 2 Wireless. Over Bluetooth, the patched controller reports the identity of an Xbox Elite controller. Apple's GameController framework then loads its Xbox driver for the controller, and that driver offers haptics and the battery level. With stock firmware, tvOS and macOS classify the controller as a generic HID gamepad with neither.

On an Apple TV 4K (3rd generation) with tvOS 27.2.1, GameController reports the category `Xbox One` for the patched controller. It lists the haptic localities `All, Default, Handles, Left Handle, Right Handle, Left Trigger, Right Trigger, Triggers` and the battery level. Core Haptics drives the motors. Every input maps to its Xbox element. macOS is untested.

| Procedure | Tested on hardware |
|---|---|
| Back up, build and write the patched image | Yes |
| Write the controller's own bank back | Yes |
| Return to stock firmware with `restore-original --write` | Partly. The writer is tested. The download of 1.09 has not run on a patched controller. |
| Return to stock firmware with 8BitDo's software | No |

## Terms

- **Stock firmware.** 8BitDo's unmodified firmware.
- **Backup.** The whole flash of one controller, read by `u2w_backup`. It contains that controller's Bluetooth pairings and calibration. Keep it private.
- **The controller's own bank.** Bank A as it is in the backup.
- **Patched image.** Bank A with the edits in this package, built from the controller's own bank.
- **Writer.** `u2w_backup.restore.run`, the code behind `restore-original`. `u2w_xbox.write` runs it with the patched image in place of 1.09.
- **Update mode.** The bootloader's USB mode for reading and writing the flash. The controller appears as `2dc8:3208`, "8BitDo Boot".

## Requirements

- A Mac with Python 3.12 or later. Run every command from the root of this repository.
- Input Monitoring permission for the terminal app, in System Settings › Privacy & Security › Input Monitoring. After adding the permission, quit and reopen the terminal.
- A USB data cable. Unplug the 2.4 GHz adapter from every computer.
- Firmware 1.10 on the controller. 8BitDo's Ultimate Software V2 installs it. The patch compares every byte it changes with the 1.10 bytes, and it refuses any other version.

## Flash a controller

Each controller needs its own backup.

1. Update the controller to 1.10 with 8BitDo's Ultimate Software V2.
2. Turn the controller off and connect it to the Mac with the cable.
3. Back up the whole flash. This command only reads.

   ```sh
   python3 -m u2w_backup --trace sent.txt
   ```

   The command saves the backup and a report in `~/Documents/Ultimate 2 Wireless Backup/`. In the report, `firmware_version` must be `1.1`.
4. Build the patched image from the backup:

   ```sh
   python3 -m u2w_xbox.patch ~/Documents/"Ultimate 2 Wireless Backup"/backup-<date>.bin xbox.bin
   ```

   If the backup does not contain stock 1.10, the command stops with `Nothing written` and names the first address that differs.
5. Check the controller without writing. This command only reads.

   ```sh
   python3 -m u2w_xbox.write xbox.bin
   ```

   Expected output: `Check passed: it would rewrite bank A (36 sectors, 0x5000-0x29000) ...`.
6. Write the patched image. Keep the cable connected. The write takes about 1 minute.

   ```sh
   python3 -m u2w_xbox.write xbox.bin --write --trace sent.txt
   ```

   Expected output at the end: `Back after ... s as 2dc8:310b; by cable its firmware reads as ...`, then `done`. These messages name 1.09, because the writer's wording names 1.09. The bytes written come from `xbox.bin`.
7. Unplug the cable and set the mode switch to BT.
8. On every device that the controller was paired with, forget the controller in the Bluetooth settings. A device that keeps the old pairing can also keep the old description of the controller.
9. Hold Pair for 3 seconds, and pair the controller again. The controller name does not change.
10. Check the result with `tvos/rumble-test` on an Apple TV, or with the controller test app on a Mac (`macos/u2w/build-test.sh`). The category must be `Xbox One`, and the haptic localities must be listed.

## Return to stock firmware

`restore-original` downloads stock firmware from 8BitDo's update server, checks its SHA-256 and writes it. The server offers 1.09 for this controller. The writer compares the controller's bootloader with the backup from step 3 of "Flash a controller", so that backup must exist.

1. Connect the controller to the Mac with the cable. The controller can be on or off.
2. Check without writing:

   ```sh
   python3 -m u2w_backup restore-original
   ```

3. Write stock firmware. Keep the cable connected.

   ```sh
   python3 -m u2w_backup restore-original --write --trace sent.txt
   ```

   Expected output at the end: `done 8BitDo's firmware 1.09 restored`.
4. To install 1.10 again, update the controller with 8BitDo's Ultimate Software V2.
5. On every device that the controller was paired with, forget the controller, then pair it again.

### Recovery when the controller does not start or does not answer by cable

1. Turn the controller fully off: unplug the cable, then hold Home for about 12 seconds.
2. Hold LB + RB, and plug the cable in. The controller enters update mode. Update mode is part of the bootloader, and no command in this repository writes the bootloader.
3. Run step 3 of "Return to stock firmware". The writer detects update mode and writes from there.

To leave update mode without writing, run `python3 -m u2w_backup leave-update-mode`, or unplug the cable and hold Home for about 12 seconds. `leave-update-mode` restarts the controller only when bank A contains a whole firmware.

### Write back the controller's own bank

The same writer writes the controller's own bank back from the backup:

```sh
python3 -m u2w_xbox.patch --stock ~/Documents/"Ultimate 2 Wireless Backup"/backup-<date>.bin stock.bin
python3 -m u2w_xbox.write stock.bin --write --trace sent.txt
```

## What the patch changes

The patch changes only the Bluetooth interface. USB mode, 2.4 GHz mode and the rest of the firmware are unchanged.

| Edit | Address | Stock firmware | Patched image |
|---|---|---|---|
| PnP ID | `0x1b54c` | `2dc8:6012` | `045e:0b22`, Xbox Elite V2 |
| HID report map | `0x1b4d8` | 113 bytes: input report 1 of 33 bytes, output report 5 | 98 bytes: input report 1 of 19 bytes, output report 3 |
| Report map length in the GATT table | `0x1b92c` | `0x71` | `0x62` |
| Input report notify | `0xe458` | `notify(0x40, 0x1d, payload, 33)` | call to the cave |
| Cave | `0x1c780` | zero padding with no references | `cave.s`: builds the Xbox input report and sends it with length 19 |
| Rumble callback | `0xd53e` | motors from value bytes 0 and 1 | call to the rumble routine |
| Rumble routine | `0x1c7f0` | zero padding with no references | `rumble.s`: motor strengths from the Xbox packet, converted to 0-255 |
| Output report reference | `0x1c6f0` | `05 02` | `03 02` |
| CRC and start-up sum | `0x1ca60` | | recomputed |

**Input report.** The first 9 bytes of the stock input report have the same layout as on the Ultimate 2C: hat (0-7, 15 when released), LX, LY, RX, RY, RT, LT, then the button bits. The cave writes the 19-byte Xbox Elite input report: sticks as 16-bit values, triggers as 10-bit values, the hat as 1-8 with 0 when released, and the buttons at the Xbox bit positions. Each trigger value is `v << 2 | v >> 6`, so 255 gives 1023.

**Rumble path.** Stock firmware drives the motors from output report 5, through the write callback at `0xd534` and the motor routine at `0x12220`. The motor routine takes strengths from 0 to 255. The output routine at `0x12114` sets a PWM duty of `20 + strength × 80 / 255` percent.

The patch changes the report ID to 3, and the callback calls the rumble routine, `rumble.s`. The routine reads the Xbox packet `[0f LT RT LOW HIGH ff 00 eb]`, where each strength runs from 0 to 100. The controller has motors in the handles only. The left motor gets the larger of LT and LOW, and the right motor gets the larger of RT and HIGH. The routine multiplies each strength by 164, shifts it right by 6 and caps it at 255, so 100 becomes 255.

**Integrity checks.** Bank A contains two checks over its first `hsize - 4` bytes, where `hsize` is the header word at `+0x18`: a Telink CRC at `hsize - 4`, and the start-up sum at `hsize`. The patch recomputes both. At start-up, the bootloader runs bank A only when the sum matches. According to the bootloader code, a failed sum makes the bootloader copy bank B, the second firmware copy at `0x32000`, over bank A. No test has shown that copy yet.

**Not included.** The patched image does not report L4, R4, M1 and M2, because the Xbox input report has no field that GameController reads for them. It also drops the motion data and the digital trigger bits. On tvOS, the system handles Home and does not pass it to apps.

## Rebuild the cave and the rumble routine

The Telink tc32 toolchain assembles `cave.s`. Use the `macos` branch of flyskywhy/tc32. Its binaries are x86_64 and run under Rosetta. Link the cave at its address, with the two firmware addresses that it calls:

```sh
tc32-elf-as -o cave.o cave.s
tc32-elf-ld -Ttext=0x1c780 --defsym=notify=0x188d0 --defsym=back=0xe464 -o cave.elf cave.o
tc32-elf-objcopy -O binary --only-section=.text cave.elf cave.bin
```

Build the rumble routine the same way, linked at its own address:

```sh
tc32-elf-as -o rumble.o rumble.s
tc32-elf-ld -Ttext=0x1c7f0 -o rumble.elf rumble.o
tc32-elf-objcopy -O binary --only-section=.text rumble.elf rumble.bin
```

`CAVE` and `RUMBLE_ROUTINE` in `patch.py` hold the resulting bytes. After any change, disassemble the patched bank with `tc32-elf-objdump -D -b binary -m tc32 --adjust-vma=0x5000`, and check that every branch target is the intended address.
