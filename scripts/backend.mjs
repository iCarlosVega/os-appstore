import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

if (existsSync(".env")) process.loadEnvFile(".env");
const python = process.env.PYTHON || resolve("backend/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
if (!existsSync(python) && !process.env.PYTHON) {
  console.error("Set up FastAPI first: python3 -m venv backend/.venv, then backend/.venv/bin/python -m pip install -r backend/requirements.txt");
  process.exit(1);
}
const [command = "serve", ...options] = process.argv.slice(2);
const serving = command === "serve";
const args = serving
  ? ["-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", process.env.API_HOST || "127.0.0.1", "--port", process.env.API_PORT || "8000", ...options]
  : ["-m", "app.cli", command, ...options];
const child = spawn(python, args, { cwd: serving ? process.cwd() : resolve("backend"), stdio: "inherit", env: process.env });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("error", error => { console.error(`Could not start FastAPI backend: ${error.message}`); process.exitCode = 1; });
child.on("exit", (code, signal) => { process.exitCode = code ?? (signal === "SIGINT" || signal === "SIGTERM" ? 0 : 1); });
