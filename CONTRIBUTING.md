# Contributing

Thank you for helping. This project writes firmware to a controller that people use every day, so it has a few rules
that decide what can be merged and how.

## What needs testing on hardware

- **Anything that changes what is written to the controller or the dongle must be tested on the real device before it
  is merged.** That covers `firmware-src/`, the tweak recipes, the stock hashes, and the code that erases, writes or
  restores. The maintainer tests it on the maintainer's own Ultimate 2C and dongle; the PR should say what you tested
  yourself.
- **Changes that don't write can be merged without a hardware test**, after review and with the tests passing: the
  page, the Mac app's interface, read-only diagnostics, documentation, and ports to other systems that keep the same
  core (only `u2c_customfw/transport/` changes, as `docs/porting.md` describes). A port is marked as community-tested
  until the maintainer can run it.

## Scope

- The Ultimate 2C Wireless and its 2.4 GHz dongle, on the firmware versions the app supports (controller 1.09,
  dongle 1.03). Other controllers, other firmware versions and platforms the maintainer can't run are best released
  from your own fork. The code is GPL-3.0, so you're free to do that.

## Safeguards

- A change must never write the bootloader (`0x0`-`0x5FFF`), erase the whole chip, or write the areas specific to one
  unit. Every edit checks the original bytes it replaces. A PR that relaxes a check in [SAFEGUARDS.md](SAFEGUARDS.md)
  won't be merged.
- When a tweak changes, the people who have it are told. A changed blob keeps its published bytes as an accepted form
  of the edit (`accepts` in `recipes.py`), so the firmware is still recognised, and the app then says that installing
  the tweaks again updates them. A new hidden tweak that comes with every install does the same for firmware without it.
  `tests/test_firmware.py` checks both, and the release notes say what changed.

## Private data and 8BitDo's firmware

- No 8BitDo firmware bytes go in the repository: stock content is known only by its SHA-256.
- Don't attach backups, MAC addresses, serial numbers or pairing data to issues or PRs. If they're needed, send them
  to github@arithon.org.

## Code

- Run `python3 -m unittest discover -s tests` before opening a PR; CI must pass. A new tweak comes with its tests.
- Contributions are licensed under GPL-3.0-or-later. Code taken from elsewhere needs a compatible licence and a line in
  [CREDITS.md](CREDITS.md); code from repositories without a licence can't be used.
- Code, comments, documentation and interface text are in English, in plain, complete sentences.

## Security

To report a security problem privately, see [SECURITY.md](SECURITY.md).
