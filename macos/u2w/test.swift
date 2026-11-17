// SPDX-License-Identifier: GPL-3.0-or-later
// Ultimate 2 Wireless Controller Test: a prototype that only reads and shows. What IOKit lists for 8BitDo devices, what
// GameController makes of each controller, every input as it moves, and two rumble tests: through GameController, and
// with 8BitDo's own output report (ID 5: strong, weak, strong, weak, 0-100) sent straight to the controller. It writes
// nothing to the controller's memory.
import AppKit
import CoreHaptics
import GameController
import IOKit.hid

final class App: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let text = NSTextView()
    let status = NSTextField(labelWithString: "")
    var seen = Set<String>()
    var engines: [CHHapticEngine] = []
    var lastNote = ""

    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 640),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Ultimate 2 Wireless Controller Test"
        window.subtitle = "Prototype · reads only"
        text.isEditable = false
        text.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        text.textContainerInset = NSSize(width: 8, height: 8)
        let scroll = NSScrollView()
        scroll.documentView = text
        scroll.hasVerticalScroller = true
        text.autoresizingMask = [.width]
        let intro = NSTextField(wrappingLabelWithString: "Connect the controller over Bluetooth, keep this window in front, and press every button, move each stick and trigger. Then click Copy Report and paste it in the issue. Home may also open Apple's Games app; that's macOS.")
        let buttons = NSStackView(views: [
            NSButton(title: "Vibrate with GameController", target: self, action: #selector(vibrate)),
            NSButton(title: "Vibrate with 8BitDo's Report", target: self, action: #selector(direct)),
            NSButton(title: "Copy Report", target: self, action: #selector(copyReport)),
            NSButton(title: "Clear", target: self, action: #selector(clear))])
        buttons.spacing = 8
        let stack = NSStackView(views: [intro, buttons, status, scroll])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 16, left: 16, bottom: 16, right: 16)
        for v in [intro, status, scroll] { v.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32).isActive = true }
        window.contentView = stack
        let menu = NSMenu(), item = NSMenuItem(), sub = NSMenu()
        sub.addItem(withTitle: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = sub
        menu.addItem(item)
        NSApp.mainMenu = menu
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        GCController.startWirelessControllerDiscovery {}
        Timer.scheduledTimer(withTimeInterval: 1.0 / 20, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // IOKit: every HID interface with 8BitDo's vendor ID, listed without opening it.
    func hidLines() -> [String] {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x2DC8] as CFDictionary)
        IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        defer { IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone)) }
        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        let p = { (d: IOHIDDevice, k: String) in IOHIDDeviceGetProperty(d, k as CFString) }
        return devices.map { d in
            let n = { (k: String) in (p(d, k) as? Int) ?? 0 }
            return String(format: "  %04x:%04x  %@  page %04x usage %04x  in %d out %d  %@", n(kIOHIDVendorIDKey), n(kIOHIDProductIDKey),
                          (p(d, kIOHIDTransportKey) as? String ?? "?"), n(kIOHIDPrimaryUsagePageKey), n(kIOHIDPrimaryUsageKey),
                          n(kIOHIDMaxInputReportSizeKey), n(kIOHIDMaxOutputReportSizeKey), (p(d, kIOHIDProductKey) as? String ?? ""))
        }.sorted()
    }

    func padLines(_ c: GCController) -> [String] {
        var out = ["  name: \(c.vendorName ?? "none")", "  category: \(c.productCategory)",
                   "  profile: \(c.extendedGamepad != nil ? "extended gamepad" : c.microGamepad != nil ? "micro gamepad" : "physical input profile only")"]
        if let h = c.haptics {
            out.append("  vibration: yes, localities \(h.supportedLocalities.map { $0.rawValue }.sorted().joined(separator: ", "))")
        } else {
            out.append("  vibration: not offered")
        }
        if let m = c.motion {
            if m.sensorsRequireManualActivation && !m.sensorsActive { m.sensorsActive = true }
            out.append(String(format: "  motion: yes, rotation rate %@, gravity %@; now rotation %.2f %.2f %.2f",
                              m.hasRotationRate ? "yes" : "no", m.hasGravityAndUserAcceleration ? "yes" : "no",
                              m.rotationRate.x, m.rotationRate.y, m.rotationRate.z))
        } else {
            out.append("  motion: not offered")
        }
        if let b = c.battery {
            out.append(String(format: "  battery: %.0f %%, state %d", b.batteryLevel * 100, b.batteryState.rawValue))
        } else {
            out.append("  battery: not reported")
        }
        let prof = c.physicalInputProfile
        var now: [String] = []
        for (name, b) in prof.buttons where b.isPressed { now.append(name); seen.insert(name) }
        for (name, a) in prof.axes where abs(a.value) > 0.2 { now.append(String(format: "%@ %.2f", name, a.value)); seen.insert(name) }
        for (name, d) in prof.dpads where abs(d.xAxis.value) > 0.2 || abs(d.yAxis.value) > 0.2 {
            now.append(String(format: "%@ %.1f,%.1f", name, d.xAxis.value, d.yAxis.value)); seen.insert(name)
        }
        out.append("  elements: \(prof.buttons.count) buttons, \(prof.axes.count) axes, \(prof.dpads.count) dpads")
        out.append("  all buttons: \(prof.buttons.keys.sorted().joined(separator: ", "))")
        out.append("  pressed now: \(now.sorted().joined(separator: ", "))")
        return out
    }

    func report() -> String {
        var lines = ["Ultimate 2 Wireless Controller Test, macOS \(ProcessInfo.processInfo.operatingSystemVersionString)", "", "IOKit (vendor 2dc8):"]
        let hid = hidLines()
        lines += hid.isEmpty ? ["  none"] : hid
        lines += ["", "GameController:"]
        let pads = GCController.controllers()
        if pads.isEmpty { lines.append("  no controller") }
        for c in pads { lines += padLines(c) + [""] }
        lines.append("Seen so far: \(seen.sorted().joined(separator: ", "))")
        if !lastNote.isEmpty { lines += ["", lastNote] }
        return lines.joined(separator: "\n")
    }

    func refresh() {
        guard NSApp.isActive else { return }
        let r = report()
        if text.string != r { text.string = r }
    }

    @objc func vibrate() {
        guard let pad = GCController.controllers().first(where: { $0.haptics != nil }) else { return say("GameController offers no vibration for any connected controller.") }
        guard let engine = pad.haptics?.createEngine(withLocality: .default) else { return say("The vibration couldn't be started.") }
        do {
            try engine.start()
            let event = CHHapticEvent(eventType: .hapticContinuous, parameters: [CHHapticEventParameter(parameterID: .hapticIntensity, value: 1)], relativeTime: 0, duration: 0.7)
            try engine.makePlayer(with: CHHapticPattern(events: [event], parameters: [])).start(atTime: CHHapticTimeImmediate)
            engines.append(engine)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in engine.stop(); self?.engines.removeAll { $0 === engine } }
            say("Sent a 0.7 s vibration through GameController.")
        } catch {
            say("GameController vibration failed: \(error.localizedDescription)")
        }
    }

    // 8BitDo's own rumble: output report 5 (strong, weak, strong, weak, 0-100), then a stop 0.7 s later, since the
    // firmware keeps the motors on until the next report.
    @objc func direct() {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x2DC8, kIOHIDProductIDKey: 0x6012] as CFDictionary)
        IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        guard let d = devices.first(where: { (IOHIDDeviceGetProperty($0, kIOHIDMaxOutputReportSizeKey as CFString) as? Int ?? 0) >= 4 }) else {
            IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
            return say("No 2dc8:6012 interface that takes an output report was found.")
        }
        let send = { (v: UInt8) -> IOReturn in let r: [UInt8] = [v, v, v, v]; return IOHIDDeviceSetReport(d, kIOHIDReportTypeOutput, 5, r, r.count) }
        let st = send(60)
        say(st == kIOReturnSuccess ? "Sent 8BitDo's report 5 at 60, and a stop 0.7 s later." : "Report 5 couldn't be sent (IOReturn \(String(UInt32(bitPattern: st), radix: 16))).")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
            _ = send(0)
            IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        }
    }

    @objc func copyReport() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(report(), forType: .string)
        say("The report is on the clipboard.")
    }

    @objc func clear() { seen.removeAll(); lastNote = ""; status.stringValue = "" }

    func say(_ s: String) { lastNote = s; status.stringValue = s }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
