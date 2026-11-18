# Rumble Test (tvOS)

Rumble Test is a diagnostics app for game controllers on Apple TV. For each connected controller, the app shows the name, the GameController category, the haptic localities, the battery and the buttons held. It has one Rumble button for each haptic locality, and it writes every event to a log.

With the patched image from `u2w_xbox`, an Ultimate 2 Wireless shows the category `Xbox One` and eight haptic localities. With stock firmware, it shows the category `HID` and no haptic localities.

## Build and install

Requirements: Xcode, XcodeGen (`brew install xcodegen`), and an Apple TV that is paired with Xcode and in developer mode.

```sh
cd tvos/rumble-test
DEVELOPMENT_TEAM=<team ID> xcodegen generate
xcrun devicectl list devices                       # the Apple TV's identifier
xcodebuild -project RumbleTest.xcodeproj -scheme RumbleTest -destination 'id=<Apple TV ID>' \
  -derivedDataPath build -allowProvisioningUpdates build
xcrun devicectl device install app --device <Apple TV ID> build/Build/Products/Debug-appletvos/RumbleTest.app
xcrun devicectl device process launch --device <Apple TV ID> --terminate-existing com.craigmdennis.RumbleTest
```

To use a different bundle identifier, change `bundleIdPrefix` in `project.yml`.

## Logs

The app writes each log line to four places:

- The screen, which shows the last 200 lines.
- `Library/Caches/rumble.log` in the app's container.
- `os.Logger` with the subsystem `com.craigmdennis.RumbleTest`, which Console.app shows.
- Standard output.

To copy the log file to the Mac:

```sh
xcrun devicectl device copy from --device <Apple TV ID> --domain-type appDataContainer \
  --domain-identifier com.craigmdennis.RumbleTest --source Library/Caches/rumble.log --destination rumble.log
```

To stream standard output, add `--console` to the launch command.

Each line starts with its type:

| Type | Content |
|---|---|
| `CONNECT`, `DISCONNECT` | The controller name. |
| `INFO` | Category, profile, haptic localities, battery, light, motion and player index. |
| `ELEMENTS` | Every input element name. |
| `BTN` | Controller name, button, press or release. The app logs values 0 and 1 only. |
| `AXIS` | Controller name, stick or pad, and position. The app logs positions past half travel only. |
| `RUMBLE`, `ENGINE` | Locality, intensity and duration, or the error. |

The app logs the Menu and B buttons and stays open. To leave the app, press the TV button on the remote.
