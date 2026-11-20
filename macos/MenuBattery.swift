// SPDX-License-Identifier: GPL-3.0-or-later
// The controller's battery in the menu bar while the app is open, to see how the charge goes. Off by default; the app
// menu's "Show Battery in Menu Bar" turns it on. It asks the core (GET /api/battery) every 30 s and goes away with the app.
import AppKit

final class MenuBattery: NSObject {
    static let key = "showBatteryInMenuBar"
    /// GET /api/battery through the core; nil when the core can't be asked yet.
    private let ask: (@escaping ([String: Any]?) -> Void) -> Void
    private var item: NSStatusItem?
    private var timer: Timer?
    private var drawn = ""   // the symbol and text last drawn: the button is only redrawn when they change
    private let line = NSMenuItem(title: "Looking for the controller…", action: nil, keyEquivalent: "")

    init(ask: @escaping (@escaping ([String: Any]?) -> Void) -> Void) { self.ask = ask }

    var shown: Bool { UserDefaults.standard.bool(forKey: Self.key) }

    func apply() { shown ? show() : hide() }

    @objc func toggle() {
        UserDefaults.standard.set(!shown, forKey: Self.key)
        apply()
    }

    private func show() {
        guard item == nil else { return refresh() }
        let status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        status.autosaveName = "u2c-battery"
        let menu = NSMenu()
        line.isEnabled = false
        menu.addItem(line)
        menu.addItem(.separator())
        let hide = NSMenuItem(title: "Hide from Menu Bar", action: #selector(toggle), keyEquivalent: "")
        hide.target = self
        menu.addItem(hide)
        status.menu = menu
        item = status
        draw(symbol: "gamecontroller", text: "")
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.refresh() }
    }

    private func hide() {
        timer?.invalidate()
        timer = nil
        if let status = item { NSStatusBar.system.removeStatusItem(status) }
        item = nil
        drawn = ""
    }

    func refresh() {
        guard item != nil else { return }
        ask { [weak self] answer in DispatchQueue.main.async { self?.update(answer) } }
    }

    private func update(_ answer: [String: Any]?) {
        guard let answer = answer, answer["busy"] as? Bool != true else { return }   // not ready, or busy: keep the last one
        let source = answer["source"] as? String
        if source == "cable", answer["unavailable"] as? Bool == true {
            line.title = "Install the tweaks again to read the battery by cable."
            return draw(symbol: "gamecontroller", text: "")
        }
        guard let percent = answer["percent"] as? Int else {
            line.title = "No controller connected by cable or over Bluetooth."
            return draw(symbol: "gamecontroller", text: "")
        }
        let full = answer["full"] as? Bool == true, charging = answer["charging"] as? Bool == true
        let how = source == "cable" ? "by cable" : "over Bluetooth"
        let name = answer["name"] as? String ?? "The controller"
        line.title = full ? "\(name) \(how): charged" : "\(name) \(how): \(percent) %\(charging ? ", charging" : "")"
        let level = percent >= 88 ? 100 : percent >= 63 ? 75 : percent >= 38 ? 50 : percent >= 13 ? 25 : 0
        draw(symbol: charging ? "battery.100percent.bolt" : "battery.\(level)percent", text: full ? "" : "\(percent) %")
    }

    /// The symbol and the percentage as one template image, which macOS tints for the menu bar and dims on a screen
    /// that isn't active.
    private func draw(symbol: String, text: String) {
        guard let button = item?.button, drawn != symbol + text else { return }
        drawn = symbol + text
        let font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.menuBarFont(ofSize: 0).pointSize, weight: .regular)
        let icon = NSImage(systemSymbolName: symbol, accessibilityDescription: "Controller battery")?
            .withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: font.pointSize, weight: .regular))
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.black]
        let textSize = (text as NSString).size(withAttributes: attributes)
        let iconSize = icon?.size ?? .zero, gap: CGFloat = text.isEmpty ? 0 : 4
        let size = NSSize(width: ceil(iconSize.width + gap + textSize.width), height: ceil(max(iconSize.height, textSize.height)))
        let image = NSImage(size: size, flipped: false) { _ in
            icon?.draw(in: NSRect(x: 0, y: (size.height - iconSize.height) / 2, width: iconSize.width, height: iconSize.height))
            (text as NSString).draw(at: NSPoint(x: iconSize.width + gap, y: (size.height - textSize.height) / 2), withAttributes: attributes)
            return true
        }
        image.isTemplate = true
        button.image = image
        button.toolTip = line.title
    }
}
