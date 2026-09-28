import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "sudonim.xps-backup"
  ipcTarget: "sudonim.xps-backup"
  property bool details: false
  property int selection: 0
  readonly property var backup: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  readonly property var info: backup ? backup.status : ({})
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property color bright: "#c0caf5"
  readonly property color accent: "#7aa2f7"
  readonly property color green: "#9ece6a"
  readonly property color amber: "#e0af68"
  readonly property color red: "#f7768e"
  readonly property color statusColor: info.state === "failure" || info.state === "due" ? red
    : info.state === "power" || info.state === "nas" || info.state === "manager" || info.state === "cancelled" || info.state === "stopping" ? amber
    : info.state === "running" ? accent : fg
  readonly property string statusSymbol: info.state === "failure" || info.state === "due" ? "⚠"
    : info.state === "power" || info.state === "nas" || info.state === "manager" || info.state === "cancelled" || info.state === "stopping" ? "Ⅱ" : ""
  readonly property string tooltip: "Backup: " + (info.headline || "Status unavailable")
    + "\nLast successful: " + (info.lastSuccessAbsolute || "None recorded")
  implicitWidth: iconButton.implicitWidth
  implicitHeight: iconButton.implicitHeight

  readonly property string actionHint: backup && backup.commandMessage ? backup.commandMessage
    : info.state === "complete" ? "Today’s backup is complete."
    : info.state === "running" ? "A backup is running. No time estimate yet."
    : info.state === "stopping" ? "Waiting for the backup to stop."
    : info.state === "unavailable" ? "Status unavailable. Last read: " + (backup ? backup.lastRead : "not yet read")
    : info.canStart ? "Retry when ready. Requires power and NAS access."
    : info.actionHint || "Waiting for an eligible backup check."
  onDetailsChanged: { scroll.contentY = 0; Qt.callLater(function() { keys.forceActiveFocus() }) }
  component InfoRow: Row {
    property string label: ""
    property string value: ""
    width: parent.width; height: 32
    Text { width: parent.width * .44; text: parent.label; color: root.fg; font.family: root.fontFamily; font.pixelSize: 12; wrapMode: Text.WordWrap }
    Text { width: parent.width * .56; text: parent.value; color: root.bright; font.family: root.fontFamily; font.pixelSize: 12; horizontalAlignment: Text.AlignRight; wrapMode: Text.WordWrap }
  }
  component DetailText: Text {
    width: parent.width; color: root.fg; font.family: root.fontFamily; font.pixelSize: 12
    textFormat: Text.PlainText; wrapMode: Text.WordWrap
  }

  onOpenedChanged: {
    if (backup) backup.panelOpen = opened
    if (opened) {
      details = false; selection = 0
      if (backup) backup.refresh()
      Qt.callLater(function() { keys.forceActiveFocus() })
    }
  }
  Component.onDestruction: if (backup) backup.panelOpen = false
  function activate() {
    if (details) { details = false; return }
    if (selection === 0) { if (backup && backup.canRequest) backup.requestDueCheck() }
    else details = true
  }

  BarIconButton {
    id: iconButton
    anchors.fill: parent
    bar: root.bar
    activeFocusOnTab: true
    Accessible.name: root.tooltip
    Keys.onReturnPressed: root.toggle()
    Keys.onEnterPressed: root.toggle()
    Keys.onSpacePressed: root.toggle()
    Rectangle {
      anchors.fill: parent
      color: "transparent"
      border.color: iconButton.activeFocus ? root.accent : "transparent"
      border.width: 2
      radius: 3
    }
    tooltipText: root.tooltip
    iconComponent: Component {
      Item {
        Canvas {
          id: drawing
          anchors.fill: parent
          onWidthChanged: requestPaint()
          onHeightChanged: requestPaint()
          onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            // Draw within a padded 19-unit optical box at every bar scale.
            ctx.save(); ctx.scale(width / 19, height / 19)
            var color = root.statusColor
            ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.6
            ctx.lineCap = "round"; ctx.lineJoin = "round"
            if (root.statusSymbol === "⚠") {
              ctx.beginPath(); ctx.moveTo(9.5, 2); ctx.lineTo(17, 17)
              ctx.lineTo(2, 17); ctx.closePath(); ctx.stroke()
              ctx.beginPath(); ctx.moveTo(9.5, 6); ctx.lineTo(9.5, 11); ctx.stroke()
              ctx.beginPath(); ctx.arc(9.5, 14, .8, 0, Math.PI*2); ctx.fill()
              ctx.restore(); return
            }
            ctx.beginPath(); ctx.arc(9.5, 9.5, 6.3, Math.PI, -Math.PI * .75, true)
            ctx.lineTo(2.4, 7); ctx.stroke()
            ctx.beginPath(); ctx.moveTo(2.4, 3.3); ctx.lineTo(2.4, 7)
            ctx.lineTo(6.1, 7); ctx.stroke()
            ctx.beginPath(); ctx.moveTo(9.5, 5.8); ctx.lineTo(9.5, 9.5)
            ctx.lineTo(12.7, 10.9); ctx.stroke()
            if (root.statusSymbol === "Ⅱ") {
              ctx.fillStyle = "#1a1b26"; ctx.fillRect(7, 6, 5, 7)
              ctx.fillStyle = color; ctx.fillRect(8, 7, 1, 5); ctx.fillRect(10, 7, 1, 5)
            }
            ctx.restore()
          }
          Connections { target: root; function onStatusColorChanged() { drawing.requestPaint() }
            function onStatusSymbolChanged() { drawing.requestPaint() } }
        }
      }
    }
    onPressed: root.toggle()
  }

  KeyboardPanel {
    id: panel
    anchorItem: iconButton
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keys
    contentWidth: panel.fittedContentWidth(root.details ? 440 : 400)
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(680))
    PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      onCloseRequested: if (root.details) root.details = false; else root.close()
      onTabRequested: function(direction) { if (!root.details) root.selection = (root.selection + direction + 2) % 2 }
      onMoveRequested: function(dx, dy) {
        if (root.details) scroll.contentY = Math.max(0, Math.min(scroll.contentHeight - scroll.height, scroll.contentY + dy * 48))
        else root.selection = Math.max(0, Math.min(1, root.selection + dy))
      }
      onActivateRequested: root.activate()
      Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
        Column {
          id: column
          width: scroll.width
          spacing: 10
          Text { text: "Backup"; color: root.bright; font.family: root.fontFamily; font.pixelSize: 14; font.bold: true }
          Text { text: root.info.backend === "borg" ? "Home snapshot → backup repository" : "Selected files → Synology"; color: root.fg; font.family: root.fontFamily; font.pixelSize: 12 }
          Column {
            visible: !root.details
            width: parent.width
            spacing: 12
            Item { width: 1; height: 6 }
            Text { width: parent.width; height: 28; text: root.info.headline || "Backup status unavailable"; color: root.statusColor; font.family: root.fontFamily; font.pixelSize: 20; font.bold: true; elide: Text.ElideRight }
            Text { width: parent.width; height: 54; text: root.info.reason || "Reading local status…"; textFormat: Text.PlainText; color: root.fg; font.family: root.fontFamily; font.pixelSize: 12; wrapMode: Text.WordWrap }
            InfoRow { label: "Last saved"; value: root.info.lastSuccess || "None recorded" }
            InfoRow { label: root.info.backend === "borg" ? "New data stored" : "Last archive size"; value: root.info.lastSize || "—" }
            InfoRow { label: root.info.state === "running" || root.info.state === "stopping" ? "Current activity" : root.info.dueLabel || "Backup due"; value: root.info.state === "running" || root.info.state === "stopping" ? root.info.currentActivity || "Checking status" : root.info.dueValue || "Unknown" }
            InfoRow { label: "Next check"; value: root.info.nextCheck || "Unavailable" }
            Rectangle { width: parent.width; height: 1; color: "#414868" }
            Text { text: "CHECKS FOR LAST SAVED BACKUP"; color: root.fg; font.family: root.fontFamily; font.pixelSize: 11; font.bold: true }
            Text { width: parent.width; text: root.info.verificationSummary || (root.info.checksPassed ? "✓ Download + 2 samples passed" : "Checks not confirmed"); color: root.info.checksPassed ? root.green : root.amber; font.family: root.fontFamily; font.pixelSize: 12 }
            Text { text: root.info.verificationTime || (root.info.checksPassed ? root.info.lastSuccess || "Time unknown" : "No verified receipt"); color: root.fg; font.family: root.fontFamily; font.pixelSize: 11 }
            Controls.Button {
              id: dueButton
              objectName: "backupAction"
              width: parent.width; height: 42
              enabled: !!root.backup && root.backup.canRequest
              text: "Back up now"
              Accessible.name: text
              onClicked: if (root.backup) root.backup.requestDueCheck()
              background: Rectangle { radius: 4; color: dueButton.enabled ? root.accent : "#2b3044"; border.color: dueButton.activeFocus || (root.selection === 0 && keys.activeFocus) ? root.bright : "transparent"; border.width: 2 }
              contentItem: Text { text: dueButton.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: dueButton.enabled ? "#1a1b26" : root.fg; font.family: root.fontFamily; font.pixelSize: 12; font.bold: true }
            }
            Text { objectName: "backupActionHint"; width: parent.width; height: 48; text: root.actionHint; textFormat: Text.PlainText; color: root.fg; font.family: root.fontFamily; font.pixelSize: 11; wrapMode: Text.WordWrap }
            Controls.Button {
              id: detailsButton
              width: parent.width; height: 32
              text: "Backup details →"
              onClicked: root.details = true
              background: Rectangle { color: "transparent"; border.color: detailsButton.activeFocus || (root.selection === 1 && keys.activeFocus) ? root.accent : "transparent"; border.width: 2 }
              contentItem: Text { text: detailsButton.text; horizontalAlignment: Text.AlignLeft; verticalAlignment: Text.AlignVCenter; color: root.accent; font.family: root.fontFamily; font.pixelSize: 12 }
            }
          }
          Column {
            visible: root.details
            width: parent.width
            spacing: 10
            Text { text: "Backup details"; color: root.bright; font.family: root.fontFamily; font.pixelSize: 20; font.bold: true }
            InfoRow { label: "Last saved"; value: root.info.lastSuccessAbsolute || "None recorded" }
            InfoRow { label: "Latest attempt"; value: root.info.lastAttemptAbsolute || root.info.lastAttempt || "Unknown" }
            InfoRow { label: "Automatic checks"; value: root.info.timerState || "Unavailable" }
            InfoRow { label: "Status last read"; value: root.backup ? root.backup.lastRead : "Not yet read" }
            Rectangle { width: parent.width; height: 1; color: "#414868" }
            DetailText { text: "CHECKS FOR LAST SAVED BACKUP"; font.bold: true }
            DetailText { text: root.info.verificationSummary || (root.info.checksPassed ? "✓ Download + 2 sample restores passed" : "Checks not confirmed"); color: root.info.checksPassed ? root.green : root.amber }
            DetailText { text: root.info.verificationTimeAbsolute || (root.info.checksPassed ? root.info.lastSuccessAbsolute || "Time unknown" : "No verified receipt") }
            DetailText { text: "Full restore: not recorded\nOff-site recovery: not verified" }
            Rectangle { width: parent.width; height: 1; color: "#414868" }
            DetailText { text: "COVERAGE"; font.bold: true }
            DetailText { text: root.info.backend === "borg" ? "Home files from a frozen filesystem snapshot, including databases and journals. Configured caches are excluded. Application consistency and full-system recovery are not guaranteed." : "Selected home files and Git work → Synology. Live databases, caches and system recovery data are excluded. This is not a full-system backup." }
            DetailText { text: "RETENTION"; font.bold: true }
            DetailText { text: root.info.retention || "Last reported inventory unavailable" }
            DetailText { text: "Automatic checks require your user session. Logging out or powering off does not guarantee a run." }
            Controls.Button {
              id: backButton
              width: parent.width; height: 36
              text: "← Back to backup"
              onClicked: root.details = false
              background: Rectangle { color: "transparent"; border.color: backButton.activeFocus || keys.activeFocus ? root.accent : "transparent"; border.width: 2 }
              contentItem: Text { text: backButton.text; verticalAlignment: Text.AlignVCenter; color: root.accent; font.family: root.fontFamily; font.pixelSize: 12 }
            }
          }
        }
      }
    }
  }
}
