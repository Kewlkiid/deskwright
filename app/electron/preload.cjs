// Narrow bridge between the renderer and the main process. No API keys ever pass through here.
const { contextBridge, ipcRenderer } = require("electron");

function listen(channel, cb) {
  const handler = (_e, ...args) => cb(...args);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

contextBridge.exposeInMainWorld("agent", {
  platform: process.platform,
  engineInfo: () => ipcRenderer.invoke("engine-info"),
  restartEngine: () => ipcRenderer.invoke("restart-engine"),
  permissions: () => ipcRenderer.invoke("permissions"),
  revokePermission: (kind) => ipcRenderer.invoke("revoke-permission", kind),
  askAccessibility: () => ipcRenderer.invoke("ask-accessibility"),
  askMicrophone: () => ipcRenderer.invoke("ask-microphone"),
  askScreen: () => ipcRenderer.invoke("ask-screen"),
  openPermission: (kind) => ipcRenderer.send("open-permission", kind),
  setMode: (mode) => ipcRenderer.send("set-mode", mode),
  setRunning: (running) => ipcRenderer.send("set-running", !!running),
  suppressEsc: () => ipcRenderer.send("suppress-esc"),
  overlay: (evt) => ipcRenderer.send("overlay", evt),
  yieldFocus: () => ipcRenderer.send("yield-focus"),
  hideForCapture: () => ipcRenderer.invoke("hide-for-capture"),
  showAfterCapture: () => ipcRenderer.send("show-after-capture"),
  revealFile: (file) => ipcRenderer.send("reveal-file", file),
  quit: () => ipcRenderer.send("quit"),
  relaunch: () => ipcRenderer.send("relaunch"),
  onGlobalStop: (cb) => listen("global-stop", cb),
  onBounds: (cb) => listen("bounds", cb),
  onEngineExit: (cb) => listen("engine-exit", cb),
});
