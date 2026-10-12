import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
if (existsSync(".env")) process.loadEnvFile(".env");
const env = { ...process.env, BACKEND_URL: process.env.BACKEND_URL || `http://127.0.0.1:${process.env.API_PORT || "8000"}` };
const backend = spawn(process.execPath, ["scripts/backend.mjs", "serve", "--reload"], { stdio: "inherit", env });
const frontend = spawn(process.execPath, [resolve("node_modules/next/dist/bin/next"), "dev", ...process.argv.slice(2)], { stdio: "inherit", env });
let stopping = false;
function stop(code) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of [backend, frontend]) if (child.exitCode === null) child.kill("SIGTERM");
}
for (const child of [backend, frontend]) {
  child.on("error", error => { console.error(error.message); stop(1); });
  child.on("exit", code => { if (!stopping) stop(code || 1); });
}
process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
