# Rumble Test (tvOS)

A diagnostics app for game controllers on Apple TV. For each connected controller it shows the name, the GameController category, the haptic localities, the battery and the buttons held, and it has one Rumble button per haptic locality. Every event goes to a log.

After `u2w_xbox` is written, an Ultimate 2 Wireless shows the category `Xbox One` and eight haptic localities. With the original firmware it shows `HID` and no haptics.

## Build and install

Requirements: Xcode, XcodeGen (`brew install xcodegen`), and an Apple TV paired with Xcode in developer mode.

```sh
cd tvos/rumble-test
DEVELOPMENT_TEAM=<team ID> xcodegen generate
xcrun devicectl list devices                       # the Apple TV's identifier
xcodebuild -project RumbleTest.xcodeproj -scheme RumbleTest -destination 'id=<Apple TV ID>' \
  -derivedDataPath build -allowProvisioningUpdates build
xcrun devicectl device install app --device <Apple TV ID> build/Build/Products/Debug-appletvos/RumbleTest.app
xcrun devicectl device process launch --device <Apple TV ID> --terminate-existing com.craigmdennis.RumbleTest
```

To use another bundle identifier, change `bundleIdPrefix` in `project.yml`.

## Logs

Each line goes to four places:

- the screen, the last 200 lines;
- `Library/Caches/rumble.log` in the app's container;
- `os.Logger`, subsystem `com.craigmdennis.RumbleTest`, visible in Console.app;
- standard output.

Copy the log file to the Mac:

```sh
xcrun devicectl device copy from --device <Apple TV ID> --domain-type appDataContainer \
  --domain-identifier com.craigmdennis.RumbleTest --source Library/Caches/rumble.log --destination rumble.log
```

Stream standard output live: add `--console` to the launch command.

Line types: `CONNECT`, `DISCONNECT`, `INFO` (category, profile, haptics, battery), `ELEMENTS`, `BTN` (press and release at values 0 and 1 only), `AXIS` (past half travel only), `RUMBLE`, `ENGINE`. The Menu and B buttons are logged and do not leave the app. Use the TV button to leave.
