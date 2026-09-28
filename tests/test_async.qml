import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
  id: test
  property var service: null
  property var panel: null
  property int step: 0
  property bool failed: false
  property var due: ({state: "due", canStart: true, serviceRunning: false, managerAvailable: true, lastCheckTime: "a"})
  property var running: ({state: "running", canStart: false, serviceRunning: true, managerAvailable: true, lastCheckTime: "b"})
  FileView { id: fixture; path: Quickshell.env("BACKUP_QML_TEST_STATE"); blockWrites: true }
  function check(ok, message) { if (!ok) { failed = true; console.error("TEST_FAILED", step, message); Qt.quit() } }
  function setFixture(value) { fixture.setText(JSON.stringify(value)) }
  Component.onCompleted: {
    var c = Qt.createComponent(Qt.resolvedUrl("Plugin/Service.qml"))
    if (c.status !== Component.Ready) { console.error("SERVICE_ERROR", c.errorString()); Qt.quit(); return }
    service = c.createObject(test)
    c = Qt.createComponent(Qt.resolvedUrl("Plugin/Panel.qml"))
    if (c.status !== Component.Ready) { console.error("PANEL_ERROR", c.errorString()); Qt.quit(); return }
    panel = c.createObject(test)
    if (service && panel) console.log("BACKUP_QML_COMPONENTS_READY")
  }
  Timer {
    interval: 20; repeat: true; running: true
    onTriggered: {
      if (!test.service || test.failed) return
      var s = test.service
      if (s.refreshing) return
      switch (test.step) {
        case 0:
          test.check(s.canRequest && s.pollInterval === 30000, "idle state")
          s.panelOpen = true; test.check(s.pollInterval === 5000, "open panel quiet polling")
          // A background poll keeps the label and action stable. A click queues
          // a fresh preflight rather than trusting the already-running sample.
          s.refresh()
          test.check(s.canRequest && s.actionLabel === "", "quiet background refresh")
          // External service starts between the prior sample and a click.
          test.setFixture(test.running)
          test.check(s.requestDueCheck() && !s.requestDueCheck(), "one preflight only")
          test.check(s.requestPhase === "waiting" && !s.canRequest, "checking state")
          test.step++; break
        case 1:
          test.check(s.status.state === "running" && !s.commandBusy && !s.canRequest, "fresh preflight suppresses redundant start")
          test.setFixture(test.due); s.refresh(); test.step++; break
        case 2:
          test.check(s.requestDueCheck(), "eligible request")
          test.step++; break
        case 3:
          if (s.requestPhase !== "confirming") return
          test.check(s.commandBusy && !s.canRequest && s.status.state === "due", "accepted request stays pending, not fake running")
          test.setFixture(test.running); s.refresh(); test.step++; break
        case 4:
          test.check(!s.commandBusy && s.status.serviceRunning && !s.canRequest && s.commandMessage === "", "running confirms and clears request message")
          test.setFixture({state:"failure",canStart:true,serviceRunning:false,managerAvailable:true,lastCheckTime:"c"}); s.refresh(); test.step++; break
        case 5:
          test.check(s.status.state === "failure" && !s.commandBusy, "failure/stop visible after running")
          test.setFixture({_fail:true}); test.check(s.requestDueCheck(), "failure preflight starts"); test.step++; break
        case 6:
          test.check(!s.commandBusy && !s.canRequest && s.status.state === "unavailable", "helper failure never sends start")
          test.setFixture(test.due); s.refresh(); test.step++; break
        case 7:
          test.check(s.requestDueCheck(), "quick completion request"); test.step++; break
        case 8:
          if (s.requestPhase !== "confirming") return
          test.setFixture({state:"complete",canStart:false,serviceRunning:false,managerAvailable:true,lastCheckTime:"d"}); s.refresh(); test.step++; break
        case 9:
          test.check(!s.commandBusy && !s.canRequest && s.status.state === "complete", "new completed check confirms without observing running")
          test.setFixture(test.due); s.refresh(); test.step++; break
        case 10:
          test.setFixture({state:"due",canStart:true,serviceRunning:false,managerAvailable:true,lastCheckTime:"a",_startFail:true})
          test.check(s.requestDueCheck(), "command failure request"); test.step++; break
        case 11:
          if (s.commandBusy) return
          test.check(s.commandMessage.indexOf("Could not request") === 0, "start failure surfaces")
          test.setFixture(test.due); s.refresh(); test.step++; break
        case 12:
          test.check(s.requestDueCheck(), "unconfirmed request"); test.step++; break
        case 13:
          if (s.requestPhase !== "confirming") return
          // Exercise the real bounded confirmation watchdog; never send a retry.
          test.step++; break
        case 14:
          if (s.commandBusy) return
          test.check(!s.canRequest && s.status.state === "unavailable" && s.commandMessage.indexOf("not confirmed") !== -1, "bounded confirmation timeout, no retry")
          if (!test.failed) console.log("BACKUP_ASYNC_GUARDS_READY")
          Qt.quit(); break
      }
    }
  }
  Timer { interval: 25000; running: true; onTriggered: { console.error("TEST_FAILED", test.step, "harness timeout"); Qt.quit() } }
}
