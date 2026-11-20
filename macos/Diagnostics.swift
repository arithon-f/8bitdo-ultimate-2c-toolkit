// SPDX-License-Identifier: GPL-3.0-or-later
// The bridge behind the page's controller test: what macOS's GameController reports, and three ways to make the
// controller vibrate. It only runs while the Diagnostics tab is open, and it never writes to the controller's memory.
import AppKit
import CoreHaptics
import GameController
import IOKit.hid
import WebKit

final class Diagnostics: NSObject, WKScriptMessageHandler {
    weak var web: WKWebView?
    private var timer: Timer?
    private var batteryTimer: Timer?
    private var lastState = ""
    private var observers: [NSObjectProtocol] = []
    private var lastInput = ""
    private var home: GCControllerButtonInput?
    private var homeWas = GCControllerElement.SystemGestureState.enabled
    private var engines: [CHHapticEngine] = []

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let op = body["op"] as? String else { return }
        switch op {
        case "start": start()
        case "stop": stop()
        case "vibrate": vibrate(body["locality"] as? String ?? "default", body["id"])
        case "direct": direct(body["id"])
        case "ring": ring(body["level"] as? Int ?? 255, body["save"] as? Bool ?? false, body["id"])
        case "quit": NSApp.terminate(nil)   // declining the disclaimer
        case "privacy":   // the Input Monitoring list, when macOS refused the controller
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent") { NSWorkspace.shared.open(url) }
        default: break
        }
    }

    /// The 2C, never a real Xbox controller connected beside it with the same IDs: the last used of the others.
    /// `current` can outlive a disconnection, so it only counts while macOS still lists it.
    private var pad: GCController? {
        let connected = GCController.controllers().filter { !realXboxNames.contains($0.vendorName ?? "") }
        if let current = GCController.current, connected.contains(current) { return current }
        return connected.first
    }

    /// The names of the real Xbox controllers connected over Bluetooth (manufacturer Microsoft), whose vendorName in
    /// GameController is that HID product name. Read when controllers come and go, not on every input.
    private var realXboxNames: Set<String> = []

    private func refreshRealXbox() {
        realXboxNames = Set(Self.bluetoothXbox().filter { Self.isRealXbox($0) }.compactMap { IOHIDDeviceGetProperty($0, kIOHIDProductKey as CFString) as? String })
    }

    private static func isRealXbox(_ device: IOHIDDevice) -> Bool {
        IOHIDDeviceGetProperty(device, kIOHIDManufacturerKey as CFString) as? String == "Microsoft"
    }

    /// The HID interfaces of 045e:0b13 pads over Bluetooth that take the 8-byte output report.
    private static func bluetoothXbox() -> [IOHIDDevice] {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x045E, kIOHIDProductIDKey: 0x0B13] as CFDictionary)
        IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        defer { IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone)) }
        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        return devices.filter {
            (IOHIDDeviceGetProperty($0, kIOHIDTransportKey as CFString) as? String)?.contains("Bluetooth") == true
                && (IOHIDDeviceGetProperty($0, kIOHIDMaxOutputReportSizeKey as CFString) as? Int ?? 0) >= 8
        }
    }

    private func start() {
        stop()
        let center = NotificationCenter.default
        for name in [Notification.Name.GCControllerDidBecomeCurrent, .GCControllerDidStopBeingCurrent, .GCControllerDidConnect, .GCControllerDidDisconnect,
                     NSApplication.didBecomeActiveNotification, NSApplication.didResignActiveNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] note in
                if note.name == .GCControllerDidConnect || note.name == .GCControllerDidDisconnect { self?.refreshRealXbox() }
                self?.sendState()
            })
        }
        refreshRealXbox()
        sendState()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in self?.sendInput() }
        refreshSystemBattery()
        batteryTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.refreshSystemBattery() }
    }

    /// Also runs when the app quits, so the Home button never stays captured.
    func stop() {
        timer?.invalidate()
        timer = nil
        batteryTimer?.invalidate()
        batteryTimer = nil
        lastState = ""
        observers.forEach(NotificationCenter.default.removeObserver)
        observers = []
        releaseHome()
        lastInput = ""
    }

    private func captureHome(_ button: GCControllerButtonInput?) {
        guard button !== home else { return }
        releaseHome()
        guard let button = button else { return }
        homeWas = button.preferredSystemGestureState
        button.preferredSystemGestureState = .disabled
        home = button
    }

    private func releaseHome() {
        home?.preferredSystemGestureState = homeWas
        home = nil
    }

    private func sendState() {
        guard let pad = pad else {
            releaseHome()
            return sendStateIfChanged(["type": "state", "connected": false])
        }
        captureHome(pad.physicalInputProfile.buttons[GCInputButtonHome])
        var state: [String: Any] = ["type": "state", "connected": true, "name": pad.vendorName ?? "Unknown controller", "category": pad.productCategory,
                                    "extended": pad.extendedGamepad != nil, "localities": localities(pad), "foreground": NSApp.isActive]
        if let battery = pad.battery, battery.batteryState != .unknown || battery.batteryLevel > 0 {
            state["battery"] = ["level": battery.batteryLevel, "state": batteryState(battery)]
        } else if let name = pad.vendorName, let percent = systemPercent[name] {
            state["battery"] = ["level": Double(percent) / 100, "state": "unknown"]
        }
        sendStateIfChanged(state)
    }

    private func sendStateIfChanged(_ state: [String: Any]) {
        guard let text = json(state), text != lastState else { return }
        lastState = text
        deliver(text)
    }

    /// pmset's reading for the current pad, taken off the main thread every 5 s; the state is sent again when it lands.
    private var systemPercent: [String: Int] = [:]
    private let pmsetQueue = DispatchQueue(label: "diagnostics.pmset")

    private func refreshSystemBattery() {
        guard let pad = pad, let name = pad.vendorName else { return sendState() }
        if let battery = pad.battery, battery.batteryState != .unknown || battery.batteryLevel > 0 { return sendState() }   // GameController knows it
        pmsetQueue.async { [weak self] in
            let percent = Self.systemBatteryPercent(of: name)
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.systemPercent[name] = percent
                self.sendState()
            }
        }
    }

    /// GameController may not report the battery of a Bluetooth pad even when macOS knows it. The public power source
    /// API only lists the Mac's own battery, so this reads `pmset`, which lists accessories too.
    private static func systemBatteryPercent(of name: String) -> Int? {
        let process = Process(), pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/pmset")
        process.arguments = ["-g", "accps"]
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        guard (try? process.run()) != nil else { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let text = String(decoding: data, as: UTF8.self)  // another accessory's name may not be valid UTF-8
        guard let line = text.split(separator: "\n").first(where: { $0.contains(name) }),
              let found = line.range(of: #"\d+(?=%)"#, options: .regularExpression) else { return nil }
        return Int(line[found])
    }

    private func batteryState(_ battery: GCDeviceBattery) -> String {
        switch battery.batteryState {
        case .charging: return "charging"
        case .discharging: return "discharging"
        case .full: return "full"
        default: return "unknown"
        }
    }

    private func localities(_ pad: GCController) -> [String] {
        guard let available = pad.haptics?.supportedLocalities else { return [] }
        return [("default", GCHapticsLocality.default), ("left", .leftHandle), ("right", .rightHandle)]
            .filter { available.contains($0.1) }.map { $0.0 }
    }

    private func sendInput() {
        guard NSApp.isActive, let e = pad?.extendedGamepad else { return }
        let buttons: [(String, GCControllerButtonInput?)] = [
            ("A", e.buttonA), ("B", e.buttonB), ("X", e.buttonX), ("Y", e.buttonY), ("LB", e.leftShoulder), ("RB", e.rightShoulder),
            ("L3", e.leftThumbstickButton), ("R3", e.rightThumbstickButton), ("View", e.buttonOptions), ("Menu", e.buttonMenu), ("Home", e.buttonHome),
            ("Up", e.dpad.up), ("Down", e.dpad.down), ("Left", e.dpad.left), ("Right", e.dpad.right)]
        let event: [String: Any] = ["type": "input", "pressed": buttons.filter { $0.1?.isPressed == true }.map { $0.0 },
                                    "lx": e.leftThumbstick.xAxis.value, "ly": e.leftThumbstick.yAxis.value,
                                    "rx": e.rightThumbstick.xAxis.value, "ry": e.rightThumbstick.yAxis.value,
                                    "lt": e.leftTrigger.value, "rt": e.rightTrigger.value]
        guard let text = json(event), text != lastInput else { return }
        lastInput = text
        deliver(text)
    }

    private func vibrate(_ locality: String, _ id: Any?) {
        let where_: GCHapticsLocality = locality == "left" ? .leftHandle : locality == "right" ? .rightHandle : .default
        guard let haptics = pad?.haptics else { return result("vibrate", "This controller doesn't offer vibration.", id) }
        guard let engine = haptics.createEngine(withLocality: where_) else { return result("vibrate", "The vibration couldn't be started.", id) }
        do {
            try engine.start()
            let strength = CHHapticEventParameter(parameterID: .hapticIntensity, value: 1)
            let event = CHHapticEvent(eventType: .hapticContinuous, parameters: [strength], relativeTime: 0, duration: 0.7)
            try engine.makePlayer(with: CHHapticPattern(events: [event], parameters: [])).start(atTime: CHHapticTimeImmediate)
            engines.append(engine)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
                engine.stop()
                self?.engines.removeAll { $0 === engine }
            }
            result("vibrate", nil, id)
        } catch {
            result("vibrate", error.localizedDescription, id)
        }
    }

    /// Xbox's rumble report straight to the controller, skipping GameController: both main motors, level 100, 0.7 s.
    private func direct(_ id: Any?) {
        send([0x03, 0x03, 0, 0, 100, 100, 70, 0, 0], "direct", id)  // report ID, then mask, LT, RT, strong, weak, duration, delay, loop
    }

    /// The Home ring tweak's marked report: bit 7 of the first byte, which no rumble mask uses, then the level and save.
    private func ring(_ level: Int, _ save: Bool, _ id: Any?) {
        send([0x03, 0x80, UInt8(clamping: level), save ? 1 : 0, 0, 0, 0, 0, 0], "ring", id)
    }

    /// The 2C over Bluetooth only: a real Xbox controller beside it has the same IDs and never gets these reports.
    private func send(_ report: [UInt8], _ op: String, _ id: Any?) {
        let ours = Self.bluetoothXbox().filter { !Self.isRealXbox($0) }
        let shown = ours.filter { IOHIDDeviceGetProperty($0, kIOHIDProductKey as CFString) as? String == pad?.vendorName }
        guard let device = shown.count == 1 ? shown.first : ours.count == 1 ? ours.first : nil else {
            return result(op, ours.isEmpty ? "No 8BitDo Ultimate 2C was found over Bluetooth."
                              : "More than one 8BitDo Ultimate 2C is connected over Bluetooth. Turn off the others and try again.", id)
        }
        // bluetoothXbox() closed its manager, and the devices with it: open this one just for the report
        let opened = IOHIDDeviceOpen(device, IOOptionBits(kIOHIDOptionsTypeNone))
        guard opened == kIOReturnSuccess else {
            return result(op, "The controller couldn't be opened (IOReturn \(String(UInt32(bitPattern: opened), radix: 16))).", id)
        }
        defer { IOHIDDeviceClose(device, IOOptionBits(kIOHIDOptionsTypeNone)) }
        let status = IOHIDDeviceSetReport(device, kIOHIDReportTypeOutput, 3, report, report.count)
        result(op, status == kIOReturnSuccess ? nil : "The report couldn't be sent (IOReturn \(String(UInt32(bitPattern: status), radix: 16))).", id)
    }

    private func result(_ op: String, _ error: String?, _ id: Any?) {
        var event: [String: Any] = ["type": "result", "op": op, "ok": error == nil]
        if let error = error { event["error"] = error }
        if let id = id { event["id"] = id }
        send(event)
    }

    private func send(_ event: [String: Any]) {
        if let text = json(event) { deliver(text) }
    }

    private func json(_ event: [String: Any]) -> String? {
        guard let data = try? JSONSerialization.data(withJSONObject: event) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func deliver(_ text: String) {
        web?.evaluateJavaScript("window.u2cDiagnostics && window.u2cDiagnostics(\(text))")
    }
}
