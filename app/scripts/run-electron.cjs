// Launch Electron with ELECTRON_RUN_AS_NODE removed. Terminals inside VS Code (itself Electron) often
// export it, which makes Electron start as plain Node and `require("electron")` return a path string.
const { spawn } = require("node:child_process");
const path = require("node:path");
const electron = require("electron");

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electron, [".", ...process.argv.slice(2)], {
  cwd: path.join(__dirname, ".."),
  env,
  stdio: "inherit",
});
child.on("exit", (code) => process.exit(code ?? 0));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
