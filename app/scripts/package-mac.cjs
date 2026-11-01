// Build Agent.app and install it in /Applications.
//   node scripts/package-mac.cjs
// The app runs the engine from this project folder (recorded in electron/root.json), so .env, saved tasks and
// the Chrome extension's pairing stay where they are; keep the folder in place after installing.
const { execSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const APP_DIR = path.resolve(__dirname, "..");
const ROOT = path.resolve(APP_DIR, "..");
const run = (cmd) => execSync(cmd, { cwd: APP_DIR, stdio: "inherit" });

fs.writeFileSync(path.join(APP_DIR, "electron", "root.json"), JSON.stringify({ root: ROOT }, null, 2) + "\n");
try {
  run("npx vite build");
  run("npx electron-builder --mac dir --publish never");
} finally {
  fs.rmSync(path.join(APP_DIR, "electron", "root.json"), { force: true }); // dev runs use the relative path
}

const built = fs.readdirSync(path.join(APP_DIR, "release")).map((d) => path.join(APP_DIR, "release", d, "Agent.app"))
  .find((p) => fs.existsSync(p));
if (!built) throw new Error("Agent.app was not built");
// Ignore ELECTRON_RUN_AS_NODE (set in VS Code terminals, it would turn the app into plain Node and exit at once).
run(`node -e "require('@electron/fuses').flipFuses(process.argv[1], {version: require('@electron/fuses').FuseVersion.V1, ` +
  `[require('@electron/fuses').FuseV1Options.RunAsNode]: false})" "${path.join(built, "Contents/MacOS/Agent")}"`);
// Sign with a stable certificate when there is one: macOS keys privacy permissions (Screen Recording,
// Accessibility) to the signature, so a stable one keeps them across rebuilds; an ad-hoc one changes every build.
const identity = (() => {
  try {
    const out = execSync("security find-identity -v -p codesigning", { encoding: "utf8" });
    const m = out.match(/"((?:Developer ID Application|Apple Development)[^"]*)"/);
    return m ? m[1] : "-";
  } catch (e) {
    return "-";
  }
})();
run(`codesign --force --deep --sign "${identity}" "${built}"`);
console.log(`Signed with: ${identity === "-" ? "ad-hoc (permissions reset on each rebuild)" : identity}`);
const target = "/Applications/Agent.app";
fs.rmSync(target, { recursive: true, force: true });
run(`ditto "${built}" "${target}"`);
console.log(`\nInstalled ${target}`);
