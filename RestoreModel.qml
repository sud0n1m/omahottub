import QtQuick
import Quickshell
import Quickshell.Io

// Restore browser state. Every NAS contact goes through the omahottub CLI;
// arguments are arrays built from archive names and index paths, never shell text.
Item {
  id: root
  property string command: Quickshell.env("HOME") + "/.local/bin/omahottub"
  property var archives: []
  property int archiveIndex: 0
  property string path: ""
  property var entries: []
  property var folderFiles: null
  property var folderBytes: null
  property string filter: ""
  property int selection: 0
  property string message: ""
  property bool error: false
  property bool loadingArchives: false
  property bool listing: false
  property bool slow: false
  property bool restoring: false
  property string restoredPath: ""
  property var pendingList: null
  readonly property string archive: archives.length > archiveIndex ? archives[archiveIndex].name : ""
  readonly property var visibleEntries: {
    var needle = filter.toLowerCase()
    return needle === "" ? entries : entries.filter(function(e) { return e.name.toLowerCase().indexOf(needle) !== -1 })
  }
  readonly property var selected: visibleEntries.length > selection ? visibleEntries[selection] : null
  readonly property bool busy: loadingArchives || listing || restoring

  signal restored(string path)

  function open() {
    message = ""; error = false; filter = ""
    if (!loadingArchives) { loadingArchives = true; archivesProcess.running = true }
  }
  function list(name, folder, wanted) {
    if (!name) return
    var request = {name: name, folder: folder, wanted: wanted === undefined ? folder : wanted}
    if (listing) { pendingList = request; return }
    listing = true; slow = false; slowTimer.restart()
    listProcess.request = request
    listProcess.command = [command, "ls", "--archive", name, "--path", folder, "--json"]
    listProcess.running = true
  }
  function selectArchive(i) {
    if (i < 0 || i >= archives.length || i === archiveIndex) return
    archiveIndex = i
    list(archive, path)  // Stay in the same folder when flipping days.
  }
  function enter(entry) {
    if (!entry || entry.type !== "d") return
    filter = ""
    list(archive, path === "" ? entry.name : path + "/" + entry.name)
  }
  function up() {
    if (path === "") return
    filter = ""
    list(archive, path.indexOf("/") === -1 ? "" : path.substring(0, path.lastIndexOf("/")))
  }
  function restore(relative) {
    if (restoring || !archive || relative === "") return
    restoring = true; error = false; restoredPath = ""
    message = "Restoring " + relative.split("/").pop() + "…"
    restoreProcess.command = [command, "restore", "--archive", archive, "--path", relative, "--json"]
    restoreProcess.running = true
  }
  function restoreSelected() { if (selected) restore(path === "" ? selected.name : path + "/" + selected.name) }
  function restoreFolder() { restore(path) }
  function fileUri(target) {
    // GVariant string literal: encode every segment, and quotes encodeURIComponent leaves alone.
    return "file://" + target.split("/").map(encodeURIComponent).join("/").replace(/'/g, "%27")
  }
  function showInFiles(target) {
    if (!target) return
    showProcess.command = ["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1",
      "--object-path", "/org/freedesktop/FileManager1", "--method", "org.freedesktop.FileManager1.ShowItems",
      "['" + fileUri(target) + "']", ""]
    showProcess.running = true
  }
  function fail(text) { error = true; message = text }
  function parse(collector, code) {
    try {
      var value = JSON.parse(collector.text)
      if (value && typeof value.error === "string") return {error: value.error}
      if (code !== 0 || !value) return {error: "Omahottub did not complete the request."}
      return value
    } catch (e) {
      return {error: code === 0 ? "Unreadable response from Omahottub." : "Omahottub is not installed or failed to start."}
    }
  }

  Timer { id: slowTimer; interval: 1500; onTriggered: root.slow = root.listing }
  Process {
    id: archivesProcess
    command: [root.command, "archives", "--json"]
    stdout: StdioCollector { id: archivesOut; waitForEnd: true }
    onExited: function(code) {
      root.loadingArchives = false
      var value = root.parse(archivesOut, code)
      if (value.error) { root.fail(value.error); return }
      var previous = root.archive
      root.archives = value.archives || []
      var keep = root.archives.findIndex(function(a) { return a.name === previous })
      root.archiveIndex = keep === -1 ? 0 : keep
      if (root.archives.length === 0) root.fail("No backups found in the repository yet.")
      else root.list(root.archive, keep === -1 ? "" : root.path)
    }
  }
  Process {
    id: listProcess
    property var request: null
    stdout: StdioCollector { id: listOut; waitForEnd: true }
    onExited: function(code) {
      var value = root.parse(listOut, code), request = listProcess.request
      root.listing = false; slowTimer.stop(); root.slow = false
      if (root.pendingList) { var next = root.pendingList; root.pendingList = null; root.list(next.name, next.folder, next.wanted); return }
      if (request.name !== root.archive) return
      if (value.error) {
        // The folder may not exist on an older day: fall back to its nearest parent.
        if (value.error.indexOf("Folder not found") === 0 && request.folder !== "") {
          root.list(request.name, request.folder.indexOf("/") === -1 ? "" : request.folder.substring(0, request.folder.lastIndexOf("/")), request.wanted)
          return
        }
        root.fail(value.error); return
      }
      if (root.path !== value.path) { root.filter = ""; root.selection = 0 }
      root.path = value.path; root.entries = value.entries || []
      root.folderFiles = value.files; root.folderBytes = value.bytes
      root.selection = Math.min(root.selection, Math.max(0, root.visibleEntries.length - 1))
      if (!root.restoring) { root.error = false; root.message = request.wanted !== value.path ? "Not in this backup; showing the nearest folder." : "" }
    }
  }
  Process {
    id: restoreProcess
    stdout: StdioCollector { id: restoreOut; waitForEnd: true }
    onExited: function(code) {
      root.restoring = false
      var value = root.parse(restoreOut, code)
      if (value.error) { root.fail(value.error); return }
      root.error = false; root.restoredPath = value.restored
      root.message = "Restored to " + value.restored.replace(Quickshell.env("HOME"), "~")
      root.restored(value.restored)
      notifyProcess.target = value.restored
      notifyProcess.command = ["notify-send", "--app-name=Omahottub", "--action=default=Show in Files",
        "Restored " + value.restored.split("/").pop(), root.message]
      notifyProcess.running = true
    }
  }
  Process {
    id: notifyProcess
    property string target: ""
    stdout: StdioCollector { id: notifyOut; waitForEnd: true }
    onExited: if (notifyOut.text.trim() === "default") root.showInFiles(target)
  }
  Process { id: showProcess }
  onFilterChanged: selection = 0
}
