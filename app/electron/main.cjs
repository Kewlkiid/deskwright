// Electron main process: the agent panel docked to the right edge, the on-screen vision overlay,
// the Python engine lifecycle and the global STOP shortcut.
const {
  app, BrowserWindow, ipcMain, globalShortcut, screen, systemPreferences, shell, session, nativeImage, desktopCapturer,
} = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

// The project folder holding engine/ (with its .venv, .env and data). In development that's two levels up; the
// installed app reads the folder recorded at build time (scripts/package-mac.cjs), unless AGENT_ROOT overrides it.
function projectRoot() {
  if (process.env.AGENT_ROOT) return process.env.AGENT_ROOT;
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, "root.json"), "utf8")).root;
  } catch (e) {
    return path.resolve(__dirname, "..", "..");
  }
}
const ROOT = projectRoot();
const ICON = path.join(__dirname, "..", "build", "icon.png");
const IS_MAC = process.platform === "darwin";
// Recording mode (`open -a Agent --args --show-in-recordings`): the panel and overlay stay visible to screen
// recordings. The engine still blanks the panel's area out of its own screenshots.
const SHOW_IN_RECORDINGS = process.argv.includes("--show-in-recordings") || process.env.AGENT_SHOW_IN_RECORDINGS === "1";
const IS_WIN = process.platform === "win32";
const IS_LINUX = process.platform === "linux";
const PANEL_WIDTH = 420;
const PANEL_MIN = 360;
const PANEL_MAX = 640;
// The corner bar is drawn 12px in from the top-right corner (Pill.tsx), in these windows and over the panel alike,
// so resizing between them moves nothing on screen. The sizes include that margin and room for the CSS shadow.
const PILL = { width: 398, height: 82 };
const MINI = { width: 110, height: 82 }; // collapsed by hand, nothing running: just the icon and the open button

let win = null;
let overlay = null;
let engine = null;
let engineInfo = null;
let engineReady = null;
let panelWidth = PANEL_WIDTH;
let mode = "panel"; // "panel": full-height right column, "pill": status bar while running, "mini": collapsed and idle
let escRegistered = false;
let ignoreEscUntil = 0;

// ---------------------------------------------------------------- engine
function pythonPath() {
  if (process.env.AGENT_PYTHON) return process.env.AGENT_PYTHON;
  const venv = IS_WIN
    ? path.join(ROOT, "engine", ".venv", "Scripts", "python.exe")
    : path.join(ROOT, "engine", ".venv", "bin", "python");
  return fs.existsSync(venv) ? venv : IS_WIN ? "python" : "python3";
}

function startEngine() {
  engineReady = new Promise((resolve) => {
    engine = spawn(pythonPath(), ["-m", "engine.main"], {
      cwd: ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["pipe", "pipe", "pipe"],
    });
    const rl = readline.createInterface({ input: engine.stdout });
    rl.on("line", (line) => {
      try {
        const msg = JSON.parse(line);
        if (msg.type === "ready") {
          engineInfo = { port: msg.port, token: msg.token };
          resolve(engineInfo);
          return;
        }
      } catch {
        /* not JSON: plain engine output */
      }
      console.log("[engine]", line);
    });
    engine.stderr.on("data", (d) => process.stderr.write(`[engine] ${d}`));
    engine.on("exit", (code) => {
      console.log(`[engine] exited with ${code}`);
      engineInfo = null;
      win?.webContents.send("engine-exit", code);
      resolve(null);
    });
    engine.on("error", (err) => {
      console.error("[engine] failed to start:", err.message);
      win?.webContents.send("engine-exit", -1);
      resolve(null);
    });
  });
  return engineReady;
}

function stopEngine() {
  if (!engine) return;
  try {
    engine.stdin.end(); // the engine exits when its stdin closes
  } catch {}
  const proc = engine;
  setTimeout(() => {
    try { proc.kill(); } catch {}
  }, 1500);
  engine = null;
}

function signalStop() {
  win?.webContents.send("global-stop");
  // Second path that works even if the renderer is busy.
  if (engine && !IS_WIN) {
    try { engine.kill("SIGUSR1"); } catch {}
  }
}

// ---------------------------------------------------------------- panel
// The panel takes the full height of the right edge of the primary display's work area and stays above
// normal windows. macOS has no API to reserve screen space, so apps can still sit underneath it; the engine
// masks this area out of screenshots so the agent never targets anything hidden behind the panel.
// While a task runs (or when collapsed by hand) the same window shrinks into a pill in the top-right corner.
function panelBounds() {
  const { workArea } = screen.getPrimaryDisplay();
  return { x: workArea.x + workArea.width - panelWidth, y: workArea.y, width: panelWidth, height: workArea.height };
}

function pillBounds(size = PILL) {
  const { workArea } = screen.getPrimaryDisplay();
  return {
    x: workArea.x + workArea.width - size.width,
    y: workArea.y,
    width: size.width,
    height: size.height,
  };
}

let docking = false;
function dock(animate = false) {
  if (!win) return;
  docking = true;
  win.setResizable(mode === "panel");
  win.setMinimumSize(mode === "panel" ? PANEL_MIN : MINI.width, 60); // the panel's minimum would stop the bar shrinking
  win.setBounds(mode === "pill" ? pillBounds() : mode === "mini" ? pillBounds(MINI) : panelBounds(), animate && IS_MAC);
  // Animated resizes emit "resize" events afterwards; keep ignoring them until the animation is over.
  setTimeout(() => {
    docking = false;
    sendBounds();
  }, animate ? 320 : 0);
}

function setMode(next) {
  if (!win || !["panel", "pill", "mini"].includes(next) || next === mode) return;
  mode = next;
  dock(false); // instant: the page animates the change (App.tsx), a native resize animation would fight it
}

function sendBounds() {
  if (!win) return;
  const b = win.getBounds();
  win.webContents.send("bounds", { ...b, mode });
  overlay?.webContents.executeJavaScript(`window.setPanel && setPanel(${JSON.stringify({ ...b, mode })})`).catch(() => {});
}

// Esc stops a running task from anywhere. Only registered while a task runs, because a global shortcut
// takes the key away from every other app. Esc presses the script itself sends are ignored.
function setRunning(running) {
  if (running && !escRegistered) {
    escRegistered = globalShortcut.register("Escape", () => {
      if (Date.now() < ignoreEscUntil) return;
      signalStop();
    });
  } else if (!running && escRegistered) {
    globalShortcut.unregister("Escape");
    escRegistered = false;
  }
}

function createWindow() {
  const b = panelBounds();
  win = new BrowserWindow({
    ...b,
    minWidth: 280,
    minHeight: 60,
    maxWidth: PANEL_MAX,
    frame: false,
    transparent: true,
    resizable: true,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    hasShadow: false,
    backgroundColor: "#00000000",
    show: false,
    icon: ICON,
    title: "Agent",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  // Exclude the agent's own window from every screenshot (macOS + Windows). Linux falls back to hiding.
  win.setContentProtection(!SHOW_IN_RECORDINGS);
  win.setAlwaysOnTop(true, "floating", 1);
  if (IS_MAC) win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  const url = process.env.ELECTRON_START_URL;
  if (url) win.loadURL(url);
  else win.loadFile(path.join(__dirname, "..", "dist", "index.html"));

  win.once("ready-to-show", () => win.show());
  // Only the width is adjustable; keep the panel pinned to the right edge at full height.
  win.on("resize", () => {
    if (docking || mode !== "panel") return;
    panelWidth = Math.max(PANEL_MIN, Math.min(PANEL_MAX, win.getBounds().width));
    dock();
  });
  // A (re)loaded renderer always starts as the full panel; bring the window back in line with it.
  win.webContents.on("did-finish-load", () => {
    mode = "panel";
    setRunning(false);
    dock();
  });
  win.on("closed", () => { win = null; });
}

function createOverlay() {
  const { bounds } = screen.getPrimaryDisplay();
  overlay = new BrowserWindow({
    ...bounds,
    frame: false,
    transparent: true,
    focusable: false,
    resizable: false,
    movable: false,
    skipTaskbar: true,
    hasShadow: false,
    alwaysOnTop: true,
    enableLargerThanScreen: true,
    show: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  overlay.setIgnoreMouseEvents(true); // click-through
  overlay.setContentProtection(!SHOW_IN_RECORDINGS); // the agent never sees its own overlay
  overlay.setAlwaysOnTop(true, "screen-saver");
  if (IS_MAC) overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  overlay.setBounds(bounds); // at screen-saver level macOS lets it cover the menu bar too (overlay.js corrects if not)
  overlay.loadFile(path.join(__dirname, "overlay.html"));
  overlay.once("ready-to-show", () => {
    overlay.showInactive();
    sendBounds();
  });
}

// ---------------------------------------------------------------- permissions
// macOS answers a process's Screen Recording check once and keeps that answer until the process restarts, so a
// grant made while Agent runs never shows up in getMediaAccessStatus. A fresh helper process gets the current answer.
// Capture itself also only works after a restart, hence `restart` once the grant is seen.
const SCREEN_AT_START = IS_MAC ? systemPreferences.getMediaAccessStatus("screen") : "granted";
let screenNow = SCREEN_AT_START;

function freshScreenStatus() {
  if (!IS_MAC || screenNow === "granted") return Promise.resolve(screenNow);
  return new Promise((resolve) => {
    const p = spawn(pythonPath(), ["-c", "import Quartz; print(bool(Quartz.CGPreflightScreenCaptureAccess()))"], {
      stdio: ["ignore", "pipe", "ignore"],
    });
    let out = "";
    p.stdout.on("data", (d) => (out += d));
    p.on("error", () => resolve(screenNow));
    p.on("close", () => {
      if (out.trim() === "True") screenNow = "granted";
      resolve(screenNow);
    });
  });
}

// Speech Recognition (the wake word) and Input Monitoring (teach mode) can only be read from a process of our own:
// the engine's Python, which macOS attributes to Agent.
const SPEECH = ["not asked", "denied", "restricted", "granted"];
function helperStatuses() {
  if (!IS_MAC) return Promise.resolve({});
  return new Promise((resolve) => {
    const code =
      "import json\nout={}\ntry:\n import Speech; out['speech']=int(Speech.SFSpeechRecognizer.authorizationStatus())\n" +
      "except Exception: pass\ntry:\n import Quartz; out['input']=bool(Quartz.CGPreflightListenEventAccess())\n" +
      "except Exception: pass\nprint(json.dumps(out))";
    const p = spawn(pythonPath(), ["-c", code], { stdio: ["ignore", "pipe", "ignore"] });
    let out = "";
    p.stdout.on("data", (d) => (out += d));
    p.on("error", () => resolve({}));
    p.on("close", () => {
      try {
        resolve(JSON.parse(out));
      } catch {
        resolve({});
      }
    });
  });
}

async function permissionStatus() {
  if (!IS_MAC) return { platform: process.platform, screen: "granted", accessibility: true, microphone: "granted" };
  const [screen, extra] = await Promise.all([freshScreenStatus(), helperStatuses()]);
  return {
    platform: process.platform,
    screen,
    restart: screen === "granted" && SCREEN_AT_START !== "granted",
    microphone: systemPreferences.getMediaAccessStatus("microphone"),
    accessibility: systemPreferences.isTrustedAccessibilityClient(false),
    speech: typeof extra.speech === "number" ? SPEECH[extra.speech] || "unknown" : "unknown",
    input: typeof extra.input === "boolean" ? extra.input : null,
  };
}

// Taking a permission back: macOS lets an app clear its own entries (tccutil reset <service> <bundle id>). The
// change shows in System Settings at once; some (Screen Recording, Accessibility) apply after Agent restarts.
const TCC_SERVICES = {
  screen: "ScreenCapture",
  accessibility: "Accessibility",
  microphone: "Microphone",
  speech: "SpeechRecognition",
  input: "ListenEvent",
  automation: "AppleEvents",
};
function revokePermission(kind) {
  const service = TCC_SERVICES[kind];
  if (!IS_MAC || !service) return Promise.resolve(false);
  const bundle = app.isPackaged ? "dev.alex.agent" : "com.github.Electron";
  return new Promise((resolve) => {
    const p = spawn("/usr/bin/tccutil", ["reset", service, bundle], { stdio: "ignore" });
    p.on("error", () => resolve(false));
    p.on("close", (code) => {
      if (kind === "screen" && code === 0) screenNow = "denied";
      resolve(code === 0);
    });
  });
}

const PANES = {
  screen: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
  accessibility: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
  microphone: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
  input: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
  speech: "x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition",
  automation: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
};

// ---------------------------------------------------------------- IPC
function registerIpc() {
  ipcMain.handle("engine-info", async () => engineInfo || (await engineReady));
  ipcMain.handle("restart-engine", async () => {
    stopEngine();
    return startEngine();
  });
  ipcMain.handle("permissions", () => permissionStatus());
  ipcMain.handle("revoke-permission", (_e, kind) => revokePermission(kind));
  ipcMain.on("relaunch", () => {
    app.relaunch();
    app.quit();
  });
  ipcMain.handle("ask-accessibility", () => (IS_MAC ? systemPreferences.isTrustedAccessibilityClient(true) : true));
  // Asking for the screen once is what puts Agent into System Settings' Screen Recording list (with macOS's prompt).
  ipcMain.handle("ask-screen", async () => {
    if (!IS_MAC) return true;
    try {
      await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 1, height: 1 } });
    } catch (e) { /* denied: the list entry still appears */ }
    return (await permissionStatus()).screen === "granted";
  });
  ipcMain.handle("ask-microphone", async () => (IS_MAC ? systemPreferences.askForMediaAccess("microphone") : true));
  ipcMain.on("open-permission", (_e, kind) => {
    if (PANES[kind]) shell.openExternal(PANES[kind]);
  });
  ipcMain.on("set-mode", (_e, next) => setMode(next));
  ipcMain.on("set-running", (_e, running) => setRunning(!!running));
  ipcMain.on("suppress-esc", () => {
    ignoreEscUntil = Date.now() + 800;
  });
  // Visual events for the on-screen overlay (Spark box, SAM mask, clicks, verdicts). Plain data only.
  ipcMain.on("overlay", (_e, evt) => {
    if (!overlay || !evt || typeof evt.type !== "string") return;
    overlay.webContents.executeJavaScript(`window.overlay && overlay(${JSON.stringify(evt)})`).catch(() => {});
  });
  // When a run starts the panel has keyboard focus (you just pressed Enter). Hand focus back to the app
  // underneath so the script's typing and shortcuts don't land in the agent's own text box.
  ipcMain.on("yield-focus", () => {
    if (!win) return;
    if (IS_MAC) {
      app.hide();
      setTimeout(() => {
        win?.showInactive();
        overlay?.showInactive();
      }, 60);
    } else {
      win.blur();
    }
  });
  // Linux has no capture exclusion: hide while the engine takes a screenshot.
  ipcMain.handle("hide-for-capture", () => {
    if (win && IS_LINUX) win.setOpacity(0);
    if (overlay && IS_LINUX) overlay.setOpacity(0);
    return true;
  });
  ipcMain.on("show-after-capture", () => {
    if (win && IS_LINUX) win.setOpacity(1);
    if (overlay && IS_LINUX) overlay.setOpacity(1);
  });
  ipcMain.on("reveal-file", (_e, file) => {
    const dataDir = path.join(ROOT, "engine", "data");
    if (typeof file === "string" && path.resolve(file).startsWith(dataDir)) shell.showItemInFolder(file);
  });
  ipcMain.on("quit", () => app.quit());
}

// ---------------------------------------------------------------- app
app.setName("Agent");

app.whenReady().then(async () => {
  if (IS_MAC && fs.existsSync(ICON)) app.dock.setIcon(nativeImage.createFromPath(ICON));
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === "media"));
  if (!process.env.ELECTRON_START_URL) {
    session.defaultSession.webRequest.onHeadersReceived((details, cb) => {
      cb({
        responseHeaders: {
          ...details.responseHeaders,
          "Content-Security-Policy": [
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
              "connect-src ws://127.0.0.1:*; media-src 'self' blob:",
          ],
        },
      });
    });
  }
  registerIpc();
  startEngine();
  createWindow();
  createOverlay();
  screen.on("display-metrics-changed", () => dock());
  const ok = globalShortcut.register("CommandOrControl+Shift+X", signalStop);
  if (!ok) console.warn("Could not register the global STOP shortcut (Cmd/Ctrl+Shift+X)");
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  stopEngine();
});

app.on("window-all-closed", () => app.quit());

// First launch: request Screen Recording right away so Agent shows up in System Settings without a manual "+".
app.whenReady().then(() => {
  if (IS_MAC && SCREEN_AT_START !== "granted") {
    desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 1, height: 1 } }).catch(() => {});
  }
});
