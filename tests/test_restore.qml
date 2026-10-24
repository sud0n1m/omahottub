import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
  id: test
  property var model: null
  property var view: null
  property int step: 0
  property bool failed: false
  property bool sawSlow: false
  property int backs: 0
  property int waits: 0
  readonly property string newest: "home-20261023T010000Z-0123abcd"
  readonly property string older: "home-20261022T010000Z-0123abcd"
  FileView { id: calls; path: Quickshell.env("RESTORE_TEST_CALLS"); blockLoading: true }
  function check(ok, message) { if (!ok) { failed = true; console.error("TEST_FAILED", step, message); Qt.quit() } }
  function find(item, name) {
    if (item.objectName === name) return item
    for (var i = 0; i < item.children.length; i++) { var hit = find(item.children[i], name); if (hit) return hit }
    return null
  }
  function key(k, modifiers, text) { return view.handleKey(k, modifiers || 0, text || "") }
  function type(text) { for (var i = 0; i < text.length; i++) key(0, 0, text[i]) }
  function logged() { calls.reload(); return calls.text().trim().split("\n").map(function(l) { return JSON.parse(l) }) }
  FloatingWindow {
    id: window
    implicitWidth: 520; implicitHeight: 640; color: "#1a1b26"
    Item { id: host; anchors.fill: parent; anchors.margins: 16 }
  }
  Component.onCompleted: {
    var c = Qt.createComponent("file://" + Quickshell.env("RESTORE_TEST_PLUGIN") + "/RestoreModel.qml")
    if (c.status !== Component.Ready) { console.error("COMPONENT_ERROR", c.errorString()); Qt.quit(); return }
    model = c.createObject(test, {command: Quickshell.env("RESTORE_TEST_BIN") + "/omahottub"})
    c = Qt.createComponent("file://" + Quickshell.env("RESTORE_TEST_PLUGIN") + "/RestoreView.qml")
    if (c.status !== Component.Ready) { console.error("COMPONENT_ERROR", c.errorString()); Qt.quit(); return }
    view = c.createObject(host, {model: model, width: 488, fontFamily: "monospace"})
    view.back.connect(function() { test.backs++ })
    model.slowChanged.connect(function() { if (model.slow) test.sawSlow = true })
  }
  Timer {
    interval: 20; repeat: true; running: true
    onTriggered: {
      if (!test.model || test.failed) return
      var m = test.model
      if (test.step > 0 && (m.busy || m.pendingList)) return
      switch (test.step) {
        case 0:
          m.open(); test.step++; break
        case 1:
          test.check(m.archives.length === 2 && m.archive === test.newest && m.path === "" && m.entries.length === 2, "archives and root listing")
          test.check(test.sawSlow && !m.slow, "slow first listing is explained, then cleared")
          test.check(test.find(test.view, "restoreDay").text.indexOf("Fri Oct 23, 18:00") === 0, "local day label")
          test.check(!test.find(test.view, "restoreFolder").enabled, "home root cannot be restored as a folder")
          test.key(Qt.Key_Down); test.check(m.selection === 1, "down"); test.key(Qt.Key_Down); test.check(m.selection === 1, "down clamps")
          test.key(Qt.Key_Up); test.key(Qt.Key_Up); test.check(m.selection === 0, "up clamps")
          test.key(Qt.Key_Return); test.step++; break
        case 2:
          test.check(m.path === "Projects" && m.folderFiles === 3 && m.folderBytes === 17, "enter folder with totals")
          test.check(test.find(test.view, "restoreFolder").enabled && test.find(test.view, "restoreFolder").text.indexOf("17 B, 3 files") !== -1, "folder action shows size")
          test.key(Qt.Key_Left, Qt.ControlModifier); test.step++; break
        case 3:
          test.check(m.archive === test.older && m.path === "" && m.message.indexOf("nearest folder") !== -1 && !m.error, "older day falls back to nearest folder")
          test.key(Qt.Key_PageUp); test.step++; break
        case 4:
          test.check(m.archive === test.newest && m.path === "", "newer day")
          test.key(Qt.Key_Right); test.step++; break
        case 5:
          test.type("read"); test.check(m.filter === "read" && m.visibleEntries.length === 1 && m.selected.name === "README.md", "typing filters, including navigation letters")
          test.key(Qt.Key_Return); test.step++; break
        case 6:
          test.check(m.error && m.message.indexOf("Already restored") === 0, "refused restore surfaces")
          test.key(Qt.Key_Backspace); test.check(m.filter === "rea", "backspace edits filter")
          test.key(Qt.Key_Escape); test.check(m.filter === "" && test.backs === 0, "escape clears filter first")
          test.key(Qt.Key_Escape); test.check(test.backs === 1, "escape then goes back")
          test.key(Qt.Key_Backspace); test.step++; break
        case 7:
          test.check(m.path === "", "backspace with empty filter goes up")
          test.key(Qt.Key_Down); test.key(Qt.Key_Return); test.step++; break
        case 8:
          test.check(!m.error && /\/Restored\/home-20261023T010000Z-0123abcd\/it's a\.txt$/.test(m.restoredPath), "restored file path")
          test.check(m.message.indexOf("Restored to ~/Restored/") === 0, "home shown as ~")
          test.key(Qt.Key_Tab); test.key(Qt.Key_Tab); test.check(test.view.focusIndex === 2, "tab reaches Show in Files")
          test.key(Qt.Key_Return); test.step++; break
        case 9:
          // The notification and Files fakes are separate processes; wait for both, bounded.
          if (++test.waits < 150 && !test.logged().some(function(r) { return r[0] === "gdbus" })) return
          test.step++; break
        case 10:
          var rows = test.logged()
          var restores = rows.filter(function(r) { return r[0] === "restore" })
          test.check(restores.length === 2 && restores.every(function(r) { return r.indexOf("--json") !== -1 && r[r.indexOf("--path") + 1] !== "" }), "two restores, never the home root")
          var notify = rows.filter(function(r) { return r[0] === "notify-send" })
          test.check(notify.length === 1 && notify[0].indexOf("--action=default=Show in Files") !== -1, "notification with action")
          var show = rows.filter(function(r) { return r[0] === "gdbus" })
          test.check(show.length === 1 && /^\['file:\/\/.*\/it%27s%20a\.txt'\]$/.test(show[0][show[0].length - 2]), "Show in Files URI is encoded: " + JSON.stringify(show))
          m.restore("crash"); test.step++; break
        case 11:
          test.check(m.error && (m.message === "Unreadable response from Omahottub." || m.message === "Omahottub is not installed or failed to start."), "crash without JSON is contained: " + m.message)
          var shot = Quickshell.env("RESTORE_TEST_SHOT")
          if (!shot) { console.log("RESTORE_BROWSER_READY"); Qt.quit(); return }
          m.message = ""; m.error = false; m.list(test.newest, "Projects"); test.step++; break
        case 12:
          window.contentItem.grabToImage(function(result) {
            result.saveToFile(Quickshell.env("RESTORE_TEST_SHOT")); console.log("RESTORE_BROWSER_READY"); Qt.quit()
          })
          test.step++; break
      }
    }
  }
  Timer { interval: 30000; running: true; onTriggered: { console.error("TEST_FAILED", test.step, "harness timeout"); Qt.quit() } }
}
