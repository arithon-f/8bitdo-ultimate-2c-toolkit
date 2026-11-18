// SPDX-License-Identifier: GPL-3.0-or-later
import SwiftUI
import GameController
import CoreHaptics
import os

// MARK: - Log: os.Logger (Console.app / Xcode), stdout (devicectl --console), file in Caches, and on screen.

final class Log: ObservableObject {
    static let shared = Log()
    @Published private(set) var lines: [String] = []
    private let logger = Logger(subsystem: "com.craigmdennis.RumbleTest", category: "diag")
    let fileURL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("rumble.log")
    private let stamp: DateFormatter = { let f = DateFormatter(); f.dateFormat = "HH:mm:ss.SSS"; return f }()

    func callAsFunction(_ msg: String) {
        let line = "\(stamp.string(from: Date())) \(msg)"
        logger.info("\(msg, privacy: .public)")
        print(line)
        if let h = try? FileHandle(forWritingTo: fileURL) {
            h.seekToEndOfFile(); h.write(Data((line + "\n").utf8)); try? h.close()
        } else {
            try? Data((line + "\n").utf8).write(to: fileURL)
        }
        DispatchQueue.main.async {
            self.lines.append(line)
            if self.lines.count > 200 { self.lines.removeFirst(self.lines.count - 200) } // ponytail: on-screen cap only, file keeps everything
        }
    }
}
let log = Log.shared

// MARK: - Controllers

final class Controllers: ObservableObject {
    @Published var list: [GCController] = []
    @Published var pressed: [ObjectIdentifier: String] = [:]
    private var engines: [String: CHHapticEngine] = [:]

    init() {
        log("--- launch, log file: \(log.fileURL.path)")
        let nc = NotificationCenter.default
        nc.addObserver(forName: .GCControllerDidConnect, object: nil, queue: .main) { [weak self] n in
            guard let c = n.object as? GCController else { return }
            log("CONNECT \(c.vendorName ?? "?")"); self?.describe(c); self?.watch(c); self?.refresh()
        }
        nc.addObserver(forName: .GCControllerDidDisconnect, object: nil, queue: .main) { [weak self] n in
            log("DISCONNECT \((n.object as? GCController)?.vendorName ?? "?")"); self?.refresh()
        }
        GCController.controllers().forEach { describe($0); watch($0) }
        refresh()
    }

    func refresh() { list = GCController.controllers() }

    func describe(_ c: GCController) {
        let haptics = c.haptics.map { h in h.supportedLocalities.map(\.rawValue).sorted().joined(separator: ",") } ?? "nil"
        let battery = c.battery.map { "\(Int($0.batteryLevel * 100))% state=\($0.batteryState.rawValue)" } ?? "n/a"
        let profile = c.extendedGamepad != nil ? "extended" : c.microGamepad != nil ? "micro" : "other"
        log("""
        INFO vendor=\(c.vendorName ?? "?") category=\(c.productCategory) profile=\(profile) \
        attached=\(c.isAttachedToDevice) haptics=[\(haptics)] battery=\(battery) \
        light=\(c.light != nil) motion=\(c.motion != nil) player=\(c.playerIndex.rawValue)
        """)
        log("ELEMENTS \(c.physicalInputProfile.elements.keys.sorted().joined(separator: ", "))")
    }

    func watch(_ c: GCController) {
        let id = ObjectIdentifier(c)
        let name = c.vendorName ?? "?"
        c.physicalInputProfile.valueDidChangeHandler = { [weak self] profile, element in
            if let b = element as? GCControllerButtonInput {
                // ponytail: skips analog trigger mid-travel spam
                if b.value == 0 || b.value == 1 { log("BTN [\(name)] \(b.localizedName ?? "?") \(b.isPressed ? "down" : "up") v=\(String(format: "%.2f", b.value))") }
            } else if let d = element as? GCControllerDirectionPad, abs(d.xAxis.value) > 0.5 || abs(d.yAxis.value) > 0.5 {
                // ponytail: only logs axes past half travel, to keep the log readable
                log("AXIS [\(name)] \(d.localizedName ?? "?") x=\(String(format: "%.2f", d.xAxis.value)) y=\(String(format: "%.2f", d.yAxis.value))")
            }
            let down = profile.buttons.values.filter(\.isPressed).compactMap(\.localizedName).sorted()
            self?.pressed[id] = down.joined(separator: " ")
        }
    }

    func rumble(_ c: GCController, locality: GCHapticsLocality, intensity: Float, seconds: Double) {
        let name = "\(c.vendorName ?? "?")/\(locality.rawValue)"
        guard let haptics = c.haptics else { log("RUMBLE \(name): controller.haptics is nil, tvOS exposes no rumble for this controller"); return }
        do {
            let key = "\(ObjectIdentifier(c))-\(locality.rawValue)"
            let engine: CHHapticEngine
            if let e = engines[key] { engine = e } else {
                guard let e = haptics.createEngine(withLocality: locality) else { log("RUMBLE \(name): createEngine returned nil"); return }
                e.stoppedHandler = { log("ENGINE \(name) stopped reason=\($0.rawValue)") }
                e.resetHandler = { log("ENGINE \(name) reset"); try? e.start() }
                engines[key] = e; engine = e
            }
            try engine.start()
            let event = CHHapticEvent(eventType: .hapticContinuous, parameters: [
                CHHapticEventParameter(parameterID: .hapticIntensity, value: intensity),
                CHHapticEventParameter(parameterID: .hapticSharpness, value: 0.5),
            ], relativeTime: 0, duration: seconds)
            try engine.makePlayer(with: CHHapticPattern(events: [event], parameters: [])).start(atTime: CHHapticTimeImmediate)
            log("RUMBLE \(name) intensity=\(intensity) \(seconds)s started")
        } catch {
            log("RUMBLE \(name) ERROR \(error)")
        }
    }
}

// MARK: - UI

@main struct RumbleTestApp: App {
    var body: some Scene { WindowGroup { ContentView() } }
}

struct ContentView: View {
    @StateObject var ctl = Controllers()
    @ObservedObject var logs = Log.shared

    var body: some View {
        HStack(alignment: .top, spacing: 40) {
            ScrollView {
                VStack(alignment: .leading, spacing: 30) {
                    if ctl.list.isEmpty { Text("No controllers. Pair one in Settings > Remotes and Devices > Bluetooth.") }
                    ForEach(ctl.list, id: \.self) { c in card(c) }
                }
            }
            .frame(width: 900)
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(logs.lines.enumerated()), id: \.offset) { i, l in
                            Text(l).font(.system(size: 18, design: .monospaced)).id(i)
                        }
                    }
                }
                .onChange(of: logs.lines.count) { _, n in proxy.scrollTo(n - 1, anchor: .bottom) }
            }
        }
        .padding(40)
        .onExitCommand { log("MENU/B pressed (exit swallowed; use the TV button to leave)") }
    }

    func card(_ c: GCController) -> some View {
        let localities = c.haptics?.supportedLocalities.sorted { $0.rawValue < $1.rawValue } ?? []
        return VStack(alignment: .leading, spacing: 10) {
            Text(c.vendorName ?? "Unknown").font(.title3).bold()
            Text("\(c.productCategory) | haptics: \(c.haptics == nil ? "none" : localities.map(\.rawValue).joined(separator: ", "))")
            Text("Battery: \(c.battery.map { "\(Int($0.batteryLevel * 100))%" } ?? "n/a")")
            Text("Held: \(ctl.pressed[ObjectIdentifier(c)] ?? "")").foregroundStyle(.secondary)
            HStack {
                ForEach(localities.isEmpty ? [GCHapticsLocality.default] : localities, id: \.self) { loc in
                    Button("Rumble \(loc.rawValue)") { ctl.rumble(c, locality: loc, intensity: 1, seconds: 1) }
                }
                Button("Info") { ctl.describe(c) }
            }
        }
    }
}
