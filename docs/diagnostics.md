# Diagnostics

The Diagnostics tab helps you check how macOS sees the controller after installing tweaks, and gather information if something goes wrong.

- **Controller test:** shows what macOS's GameController reports, which is what a game gets, including the battery when macOS provides it. Press each button, stick and trigger to see it light up, and make the controller vibrate either the way a native game would or by sending the report straight to the controller. If only the direct report vibrates, the firmware isn't the problem.
- **Firmware details:** what the app read from the controller or the dongle, including where the version came from, whether a firmware update is pending, and how the bootloader identifies itself.
- **Problem report:** a text you can attach to a bug report.
- **Battery log:** since 1.1, firmware installed with Processor rest writes down the battery's voltage and level once a minute while the controller runs on battery, in a part of its memory nothing else uses. The log stays on the controller through power-offs and holds about 270 hours; then it stops. Restoring your backup leaves it as it is. **Save Battery Log** reads it by cable and saves it as a CSV file in the app's folder, so you can send it with a problem report. It helps make the battery percentage more accurate.
- **Install Firmware 1.09 Anyway…:** the last resort for a controller whose firmware can't be identified.

The controller test is only available in the Mac app for now, because it uses macOS's GameController directly. Everything else in the tab also works when you run the app from source.
