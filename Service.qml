import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root
  property var shell: null
  property var settings: ({})
  property var status: ({state: "unavailable", headline: "Backup status unavailable",
                         reason: "Reading local status…", lastSuccess: "None recorded",
                         lastSuccessAbsolute: "None recorded", lastSize: "—",
                         dueLabel: "Due", dueValue: "Unknown", nextCheck: "Unavailable",
                         checksPassed: false, verificationLabel: "No verified receipt",
                         canStart: false, actionHint: "Status unavailable",
                         retention: "Last reported inventory unavailable", timerState: "Unavailable",
                         lastAttempt: "Unknown"})
  property string lastRead: "Not yet read"
  property bool refreshing: false
  property bool panelOpen: false
  property string requestPhase: ""
  readonly property bool commandBusy: requestPhase !== ""
  readonly property bool canRequest: !commandBusy && status.canStart === true
    && !status.serviceRunning && status.managerAvailable === true
  readonly property int pollInterval: status.serviceRunning || commandBusy ? 1000 : panelOpen ? 5000 : 30000
  readonly property string actionLabel: (requestPhase === "checking" || requestPhase === "waiting") ? "Checking status…"
    : commandBusy ? "Request pending…" : ""
  property string requestBaseline: ""
  property bool statusTimedOut: false
  property bool startTimedOut: false
  property string commandMessage: ""
  readonly property string helperPath: decodeURIComponent(String(Qt.resolvedUrl("status.py")).replace(/^file:\/\//, ""))

  function refresh() {
    if (statusProcess.running) return
    statusTimedOut = false
    refreshing = true
    statusProcess.running = true
    statusGuard.restart()
  }

  function markUnavailable() {
    status = {state: "unavailable", headline: "Backup status unavailable",
      reason: "Could not read current local status.",
      lastSuccess: status.lastSuccess || "None recorded",
      lastSuccessAbsolute: status.lastSuccessAbsolute || "None recorded",
      lastSize: status.lastSize || "—", dueLabel: "Due", dueValue: "Unknown",
      nextCheck: "Unavailable", checksPassed: status.checksPassed === true,
      verificationLabel: "Previous backup checks passed", canStart: false,
      actionHint: "Status unavailable", retention: status.retention || "Unavailable",
      timerState: "Unavailable", lastAttempt: status.lastAttempt || "Unknown",
      lastAttemptAbsolute: status.lastAttemptAbsolute || "Unknown"}
  }

  function requestDueCheck() {
    if (!canRequest) return false
    requestPhase = refreshing ? "waiting" : "checking"
    commandMessage = "Checking current status before requesting a backup…"
    refresh()
    return true
  }

  function statusReceived(parsed) {
    if (!commandBusy && parsed.state !== status.state) commandMessage = ""
    lastRead = Qt.formatDateTime(new Date(), "yyyy-MM-dd HH:mm:ss")
    if (JSON.stringify(status) !== JSON.stringify(parsed)) status = parsed
    if (requestPhase === "waiting") {
      // This sample started before the click. Obtain a new one before acting.
      requestPhase = "checking"
      refresh()
      return
    }
    if (requestPhase === "checking") {
      if (parsed.canStart === true && !parsed.serviceRunning && parsed.managerAvailable === true) {
        requestBaseline = parsed.lastCheckTime || ""
        requestPhase = "starting"
        startTimedOut = false
        commandMessage = "Requesting a due check…"
        startProcess.running = true
        startGuard.restart()
      } else {
        requestPhase = ""
        commandMessage = parsed.serviceRunning ? "A backup is already active; no new request was sent."
          : "No request sent. See the refreshed backup status."
      }
    } else if (requestPhase === "confirming"
               && (parsed.serviceRunning || (parsed.lastCheckTime && parsed.lastCheckTime !== requestBaseline))) {
      confirmationGuard.stop()
      requestPhase = ""
      commandMessage = parsed.serviceRunning ? "" : "The requested check ended. See current status."
    }
  }

  Timer { interval: root.pollInterval; repeat: true; running: true; onTriggered: root.refresh() }
  Timer { id: statusGuard; interval: 10000; onTriggered: {
    root.statusTimedOut = true; statusProcess.running = false; root.refreshing = false; root.markUnavailable()
    if ((root.requestPhase === "checking" || root.requestPhase === "waiting")) {
      root.requestPhase = ""; root.commandMessage = "Status check timed out. No backup request was sent."
    }
  } }
  Timer { id: startGuard; interval: 10000; onTriggered: {
    root.startTimedOut = true; startProcess.running = false; root.requestPhase = ""
    root.commandMessage = "Due-check request timed out. Inspect current status before retrying."
    root.refresh()
  } }
  Timer { id: confirmationGuard; interval: 15000; onTriggered: {
    root.requestPhase = ""
    root.markUnavailable()
    root.commandMessage = "Request sent, but its outcome is not confirmed. No automatic retry was made."
  } }
  Process {
    id: statusProcess
    command: ["python3", root.helperPath]
    stdout: StdioCollector { id: statusOutput; waitForEnd: true }
    onExited: function(code) {
      statusGuard.stop()
      if (root.statusTimedOut) return
      root.refreshing = false
      try {
        var parsed = JSON.parse(statusOutput.text)
        if (code !== 0 || !parsed || typeof parsed.state !== "string") throw new Error("Invalid local status")
        root.statusReceived(parsed)
      } catch (e) {
        // Keep no stale running state or enabled action after a helper failure.
        root.markUnavailable()
        if ((root.requestPhase === "checking" || root.requestPhase === "waiting")) {
          root.requestPhase = ""; root.commandMessage = "Could not check status. No backup request was sent."
        }
      }
    }
  }
  Process {
    id: startProcess
    command: ["systemctl", "--user", "start", "--no-block", root.status.backend === "borg" ? "omarchy-backup.service" : "xps-nas-backup.service"]
    stdout: StdioCollector { waitForEnd: true }
    onExited: function(code) {
      startGuard.stop()
      if (root.startTimedOut) return
      root.requestPhase = code === 0 ? "confirming" : ""
      root.commandMessage = code === 0 ? "Request accepted; waiting for current service status…"
                                        : "Could not request the due check. Inspect the user service."
      if (code === 0) confirmationGuard.restart()
      root.refresh()
    }
  }
  IpcHandler {
    target: "xps-backup"
    function status(): string { return JSON.stringify(root.status) }
    function refresh(): string { root.refresh(); return "ok" }
    function diagnostics(): string { return JSON.stringify({revision: "alpha-0.1.0-1", refreshing: root.refreshing,
      requestPhase: root.requestPhase, panelOpen: root.panelOpen, pollInterval: root.pollInterval,
      canRequest: root.canRequest}) }
  }
  Component.onCompleted: refresh()
}
