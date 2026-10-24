import QtQuick
import QtQuick.Controls as Controls

// Keyboard-first restore browser. It owns its keys so typed letters filter
// rather than navigate; the panel blocks its own key catcher while this is open.
Item {
  id: view
  property var model: null
  property string fontFamily: ""
  property color fg: "#a9b1d6"
  property color bright: "#c0caf5"
  property color accent: "#7aa2f7"
  property color red: "#f7768e"
  property int focusIndex: 0  // 0 list, 1 restore folder, 2 show in Files
  readonly property int rowHeight: 28
  readonly property var m: model || ({archives: [], visibleEntries: [], entries: []})
  signal back()
  implicitHeight: column.implicitHeight
  focus: true

  function bytes(n) {
    if (n === null || n === undefined) return ""
    var units = ["B", "KB", "MB", "GB", "TB"], i = 0
    while (n >= 1000 && i < units.length - 1) { n /= 1000; i++ }
    return (i === 0 ? n : n.toFixed(n < 10 ? 1 : 0)) + " " + units[i]
  }
  function day(a) {
    if (!a) return "No backup selected"
    var d = new Date(a.time.substring(0, 19))
    return isNaN(d.getTime()) ? a.name : Qt.formatDateTime(d, "ddd MMM d, HH:mm")
  }
  function shown(name) { return name.replace(/\n/g, "⏎") }
  function focusCount() { return m.restoredPath ? 3 : 2 }
  function activate() {
    if (!model) return
    if (focusIndex === 1) model.restoreFolder()
    else if (focusIndex === 2) model.showInFiles(model.restoredPath)
    else if (model.selected && model.selected.type === "d") model.enter(model.selected)
    else model.restoreSelected()
  }
  function reset() { focusIndex = 0; list.positionViewAtBeginning() }

  // Returns whether the key was used; tests drive this directly.
  function handleKey(key, modifiers, text) {
    if (!model) return false
    var ctrl = modifiers & Qt.ControlModifier
    if (key === Qt.Key_Escape) { if (model.filter !== "") model.filter = ""; else view.back() }
    else if (key === Qt.Key_Tab) focusIndex = (focusIndex + 1) % focusCount()
    else if (key === Qt.Key_Backtab) focusIndex = (focusIndex + focusCount() - 1) % focusCount()
    else if ((ctrl && key === Qt.Key_Left) || key === Qt.Key_PageDown) model.selectArchive(model.archiveIndex + 1)
    else if ((ctrl && key === Qt.Key_Right) || key === Qt.Key_PageUp) model.selectArchive(model.archiveIndex - 1)
    else if (key === Qt.Key_Up) { focusIndex = 0; model.selection = Math.max(0, model.selection - 1) }
    else if (key === Qt.Key_Down) { focusIndex = 0; model.selection = Math.max(0, Math.min(model.visibleEntries.length - 1, model.selection + 1)) }
    else if (key === Qt.Key_Right && focusIndex === 0) { if (model.selected) model.enter(model.selected) }
    else if (key === Qt.Key_Left) { focusIndex = 0; model.up() }
    else if (key === Qt.Key_Return || key === Qt.Key_Enter) activate()
    else if (key === Qt.Key_Backspace) { if (model.filter !== "") model.filter = model.filter.slice(0, -1); else model.up() }
    else if (!ctrl && text && text.length === 1 && text >= " ") { focusIndex = 0; model.filter += text }
    else return false
    return true
  }
  Keys.onPressed: function(event) { event.accepted = handleKey(event.key, event.modifiers, event.text) }

  Column {
    id: column
    width: parent.width
    spacing: 10
    Row {
      width: parent.width; height: 28; spacing: 8
      Controls.Button {
        id: older
        width: 28; height: 28; text: "‹"
        enabled: !!view.model && view.model.archiveIndex < view.m.archives.length - 1
        Accessible.name: "Older backup"
        onClicked: view.model.selectArchive(view.model.archiveIndex + 1)
        background: Rectangle { radius: 4; color: older.hovered ? "#2b3044" : "transparent" }
        contentItem: Text { text: older.text; color: older.enabled ? view.accent : "#414868"; font.family: view.fontFamily; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
      }
      Text {
        objectName: "restoreDay"
        width: parent.width - 2 * 28 - 2 * 8; height: 28
        text: view.m.archives.length ? view.day(view.m.archives[view.m.archiveIndex]) + "   " + (view.m.archiveIndex + 1) + " of " + view.m.archives.length
          : view.m.loadingArchives ? "Loading backups…" : "No backups"
        color: view.bright; font.family: view.fontFamily; font.pixelSize: 16; font.bold: true
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
      }
      Controls.Button {
        id: newer
        width: 28; height: 28; text: "›"
        enabled: !!view.model && view.model.archiveIndex > 0
        Accessible.name: "Newer backup"
        onClicked: view.model.selectArchive(view.model.archiveIndex - 1)
        background: Rectangle { radius: 4; color: newer.hovered ? "#2b3044" : "transparent" }
        contentItem: Text { text: newer.text; color: newer.enabled ? view.accent : "#414868"; font.family: view.fontFamily; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
      }
    }
    Text {
      objectName: "restorePath"
      width: parent.width
      text: "~/" + view.shown(view.m.path || "") + (view.m.filter ? "   filter: " + view.m.filter : "")
      textFormat: Text.PlainText; color: view.fg; font.family: view.fontFamily; font.pixelSize: 12; elide: Text.ElideMiddle
    }
    Rectangle {
      width: parent.width; height: view.rowHeight * 11; radius: 4; color: "#16161e"
      border.color: view.focusIndex === 0 && view.activeFocus ? "#414868" : "transparent"
      ListView {
        id: list
        objectName: "restoreList"
        anchors.fill: parent; anchors.margins: 1
        clip: true
        model: view.m.visibleEntries
        currentIndex: view.m.selection || 0
        boundsBehavior: Flickable.StopAtBounds
        onCurrentIndexChanged: positionViewAtIndex(currentIndex, ListView.Contain)
        Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
        delegate: Rectangle {
          required property var modelData
          required property int index
          width: list.width; height: view.rowHeight
          color: index === view.m.selection ? (view.focusIndex === 0 ? "#2b3044" : "#20232f") : "transparent"
          Text {
            x: 10; width: 18; height: parent.height
            text: modelData.type === "d" ? "▸" : modelData.type === "l" ? "↪" : ""
            color: view.accent; font.family: view.fontFamily; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter
          }
          Text {
            x: 28; width: parent.width - 128; height: parent.height
            text: view.shown(modelData.name)
            textFormat: Text.PlainText; color: modelData.type === "d" ? view.bright : view.fg
            font.family: view.fontFamily; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
          }
          Text {
            x: parent.width - 96; width: 86; height: parent.height
            text: modelData.type === "-" ? view.bytes(modelData.size) : ""
            color: view.fg; font.family: view.fontFamily; font.pixelSize: 11; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter
          }
          MouseArea {
            anchors.fill: parent
            onClicked: { view.focusIndex = 0; view.model.selection = index; view.forceActiveFocus() }
            onDoubleClicked: { view.model.selection = index; view.activate() }
          }
        }
      }
      Text {
        anchors.centerIn: parent; width: parent.width - 40
        visible: view.m.listing || view.m.loadingArchives || (!view.m.visibleEntries.length && !!view.m.archive)
        text: view.m.slow ? "Reading this day's file list from your backup.\nThe first look at each day takes longer."
          : view.m.listing || view.m.loadingArchives ? "Loading…"
          : view.m.filter ? "Nothing here matches “" + view.m.filter + "”." : "This folder is empty."
        color: view.fg; font.family: view.fontFamily; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
      }
    }
    Controls.Button {
      id: folderButton
      objectName: "restoreFolder"
      width: parent.width; height: 38
      enabled: !!view.model && view.model.path !== "" && !view.model.busy
      text: view.m.path ? "Restore this folder · " + view.bytes(view.m.folderBytes) + ", " + (view.m.folderFiles || 0).toLocaleString(Qt.locale(), "f", 0) + " files"
        : "Open a folder to restore all of it"
      onClicked: view.model.restoreFolder()
      background: Rectangle { radius: 4; color: folderButton.enabled ? view.accent : "#2b3044"; border.color: view.focusIndex === 1 && view.activeFocus ? view.bright : "transparent"; border.width: 2 }
      contentItem: Text { text: folderButton.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: folderButton.enabled ? "#1a1b26" : view.fg; font.family: view.fontFamily; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight }
    }
    Text {
      objectName: "restoreMessage"
      width: parent.width; height: 34
      text: view.m.message || "Restores go to ~/Restored/ and never replace your current files."
      textFormat: Text.PlainText; color: view.m.error ? view.red : view.fg; font.family: view.fontFamily; font.pixelSize: 11; wrapMode: Text.WordWrap; elide: Text.ElideRight
    }
    Controls.Button {
      id: showButton
      width: parent.width; height: 28
      visible: !!view.m.restoredPath
      text: "Show in Files →"
      onClicked: view.model.showInFiles(view.model.restoredPath)
      background: Rectangle { color: "transparent"; border.color: view.focusIndex === 2 && view.activeFocus ? view.accent : "transparent"; border.width: 2 }
      contentItem: Text { text: showButton.text; verticalAlignment: Text.AlignVCenter; color: view.accent; font.family: view.fontFamily; font.pixelSize: 12 }
    }
    Text {
      width: parent.width
      text: "↑↓ select · ⏎ open or restore · ← up · type to filter\nCtrl+←/→ change day · Tab restore folder · Esc back"
      color: "#565f89"; font.family: view.fontFamily; font.pixelSize: 10; wrapMode: Text.WordWrap
    }
    Controls.Button {
      id: backButton
      width: parent.width; height: 32
      text: "← Back to backup"
      onClicked: view.back()
      background: Rectangle { color: "transparent" }
      contentItem: Text { text: backButton.text; verticalAlignment: Text.AlignVCenter; color: view.accent; font.family: view.fontFamily; font.pixelSize: 12 }
    }
  }
}
