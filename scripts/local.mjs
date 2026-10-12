import { spawn, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, lstatSync, readFileSync, writeFileSync } from "node:fs";
import { createConnection } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseEnv } from "node:util";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const envFile = resolve(root, ".env.development.local");
const [command, ...options] = process.argv.slice(2);
const commands = ["setup", "db-up", "db-down", "dev", "worker", "migrate", "import-catalog"];

class LocalError extends Error {}
function fail(message) { throw new LocalError(message); }

function localEnvironment() {
  if (!existsSync(envFile)) fail("Missing .env.development.local. Run npm run local:setup first.");
  if (!lstatSync(envFile).isFile()) fail(".env.development.local must be a regular file in this worktree.");
  const local = parseEnv(readFileSync(envFile, "utf8"));
  const password = local.POSTGRES_PASSWORD || "";
  if (!/^[A-Za-z0-9_-]+$/.test(password) || local.DATABASE_URL !== `postgresql://store:${password}@127.0.0.1:55432/os_appstore_development`) {
    fail("Local DATABASE_URL must match POSTGRES_PASSWORD and the dedicated loopback PostgreSQL destination; see .env.development.example.");
  }
  const env = { ...process.env, ...local };
  // libpq environment settings can reroute even an explicitly configured URL.
  for (const key of Object.keys(env)) if (key.startsWith("PG")) delete env[key];
  for (const key of ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "OWNER_GITHUB_ID", "AUTH_SECRET", "GITHUB_TOKEN", "TYPESAFE_API_KEY", "DISCORD_WEBHOOK_URL", "BACKEND_PROXY_SECRET"]) {
    env[key] = local[key] || "";
  }
  return {
    ...env, STORE_LOCAL: "1", STORE_ENV_FILE: envFile, APP_ENV: "development", NODE_ENV: "development",
    APP_URL: "http://localhost:3000", BACKEND_URL: "http://127.0.0.1:8000", API_HOST: "127.0.0.1", API_PORT: "8000",
    PYTHON: resolve(root, "backend/.venv/bin/python"),
    SQLITE_PATH: resolve(root, ".data/local-postgres/unused.sqlite"), BACKUP_DIR: resolve(root, ".data/local-postgres/backups"),
    TYPESAFE_MODEL: local.TYPESAFE_MODEL || "jev-1.13.0",
  };
}

function checkPython(env) {
  if (!existsSync(env.PYTHON)) fail("Missing worktree Python. Run python3 -m venv backend/.venv, then backend/.venv/bin/python -m pip install -r backend/requirements.txt.");
  if (!existsSync(resolve(root, "backend/app/schema.py"))) fail("Migration lane is not integrated: backend/app/schema.py is missing. Integrate migrations before using local Python commands.");
  const result = spawnSync(env.PYTHON, ["-c", "import fastapi, uvicorn, httpx, dotenv, psycopg, alembic, sqlalchemy"], { cwd: root, env, stdio: "ignore", timeout: 10000 });
  if (result.status !== 0) fail("Worktree Python dependencies are unavailable. Install the integrated backend/requirements.txt into backend/.venv.");
}

async function requireFreePort(port) {
  for (const host of ["127.0.0.1", "::1"]) {
    const occupied = await new Promise((resolvePort, reject) => {
      const socket = createConnection({ host, port });
      socket.once("connect", () => { socket.destroy(); resolvePort(true); });
      socket.once("error", error => {
        socket.destroy();
        if (["ECONNREFUSED", "EAFNOSUPPORT", "ENETUNREACH", "EADDRNOTAVAIL"].includes(error.code)) resolvePort(false);
        else reject(new LocalError(`Cannot check local port ${port}; check local networking permissions.`));
      });
      socket.setTimeout(2000, () => { socket.destroy(); reject(new LocalError(`Timed out checking local port ${port}.`)); });
    });
    if (occupied) fail(`Port ${port} is occupied. Stop the service using it explicitly, then retry; local endpoints are fixed.`);
  }
}

function run(executable, args, env) {
  return new Promise(resolveRun => {
    const child = spawn(executable, args, { cwd: root, env, stdio: "inherit" });
    const interrupt = () => child.kill("SIGINT");
    const terminate = () => child.kill("SIGTERM");
    process.on("SIGINT", interrupt);
    process.on("SIGTERM", terminate);
    child.once("error", () => { console.error("Could not launch local command; check the required executable and permissions."); });
    child.once("close", (code, signal) => {
      process.off("SIGINT", interrupt);
      process.off("SIGTERM", terminate);
      resolveRun(code ?? (signal === "SIGINT" ? 130 : signal === "SIGTERM" ? 143 : 1));
    });
  });
}

async function main() {
  if (!commands.includes(command)) fail(`Usage: node scripts/local.mjs <${commands.join("|")}> [options]`);
  if (process.platform === "win32") fail("local:* commands require a POSIX host (macOS/Linux) for child-process cleanup. Use the original non-local workflow on Windows.");
  if (options.length && command !== "import-catalog" && !(command === "worker" && options.length === 1 && options[0] === "--once")) {
    fail("Only import-catalog accepts import flags; worker accepts --once. Other local commands take no options.");
  }
  if (command === "setup") {
    const template = readFileSync(resolve(root, ".env.development.example"), "utf8");
    try {
      writeFileSync(envFile, template.replaceAll("REPLACE_WITH_GENERATED_PASSWORD", randomBytes(32).toString("hex")), { flag: "wx", mode: 0o600 });
      console.log("Created private .env.development.local. Existing SQLite and production configuration are unchanged.");
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      console.log(".env.development.local already exists; kept unchanged.");
    }
    return 0;
  }
  const env = localEnvironment();
  if (command === "db-up" || command === "db-down") {
    const compose = ["compose", "--env-file", envFile, "-p", "os-appstore-local", "-f", resolve(root, "compose.local.yaml")];
    const version = spawnSync("docker", ["compose", "version"], { cwd: root, env, stdio: "ignore", timeout: 10000 });
    if (version.status !== 0) fail("Docker Compose is unavailable. Install Docker with Compose v2 or later.");
    const context = spawnSync("docker", ["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], { cwd: root, env, encoding: "utf8", timeout: 10000 });
    const contextHost = context.status === 0 ? context.stdout.trim() : "";
    const dockerHost = env.DOCKER_CONTEXT ? contextHost : env.DOCKER_HOST || contextHost;
    if (!dockerHost.startsWith("unix:///")) fail("Local database commands require a local Unix Docker socket/context; remote Docker endpoints are refused.");
    const engine = spawnSync("docker", ["info", "--format", "{{.ServerVersion}}"], { cwd: root, env, stdio: "ignore", timeout: 10000 });
    if (engine.status !== 0) fail("Docker engine is unavailable. Start your local Docker engine and retry.");
    if (command === "db-up") {
      const status = spawnSync("docker", [...compose, "ps", "--status", "running", "--quiet", "db"], { cwd: root, env, encoding: "utf8", timeout: 10000 });
      if (status.status !== 0) fail("Cannot inspect the local Compose project; check Docker configuration.");
      if (!status.stdout.trim()) await requireFreePort(55432);
    }
    return run("docker", [...compose, ...(command === "db-up" ? ["up", "-d", "--wait", "--wait-timeout", "90"] : ["down"])], env);
  }
  checkPython(env);
  if (command === "dev") {
    if (!existsSync(resolve(root, "node_modules/next/dist/bin/next"))) fail("Missing worktree Node dependencies. Run npm ci here first.");
    await requireFreePort(8000);
    await requireFreePort(3000);
    return run(process.execPath, ["scripts/dev.mjs"], env);
  }
  if (command === "import-catalog") {
    if (!existsSync(resolve(root, "backend/app/catalog_import.py"))) fail("Catalog import lane is not integrated: backend/app/catalog_import.py is missing.");
    return run(env.PYTHON, ["-m", "backend.app.catalog_import", ...options], env);
  }
  return run(process.execPath, ["scripts/backend.mjs", command, ...options], env);
}

try { process.exitCode = await main(); }
catch (error) {
  console.error(error instanceof LocalError ? error.message : "Local command failed. Check file permissions and local configuration.");
  process.exitCode = 1;
}
