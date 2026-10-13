import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";

const filename = new URL("../src/lib/community-types.ts", import.meta.url);
assert.ok(existsSync(filename), "Community UI response/state helpers must exist");
const source = ts.transpileModule(readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const module = { exports: {} };
new Function("module", "exports", "require", source)(module, module.exports, createRequire(import.meta.url));
const { initialSearchState, searchReducer, searchEndpoint, repositorySelection,
  initialRequestState, requestReducer, submissionMessage, searchErrorMessage } = module.exports;

// Frozen HTTP fixtures: provider and backend calls never leave this process.
const repository = { repoId: "9007199254740993", repoUrl: "https://github.com/example/editor",
  name: "editor", owner: "example", description: "An offline editor", stars: 42,
  license: "MIT", archived: false, status: "available", suggestionCount: 0 };
let checks = 0;
function check(name, run) { run(); checks++; console.log(`PASS ${name}`); }

check("late search A and errors cannot replace newer B or a cleared query", () => {
  let state = searchReducer(initialSearchState, { type: "query", query: "alpha" });
  const first = state.generation;
  state = searchReducer(state, { type: "query", query: "beta" });
  const second = state.generation;
  state = searchReducer(state, { type: "results", generation: second, result: { items: [repository], incomplete: true } });
  assert.equal(state.items[0].repoId, "9007199254740993");
  assert.equal(state.incomplete, true);
  assert.strictEqual(searchReducer(state, { type: "results", generation: first, result: { items: [], incomplete: false } }), state);
  assert.strictEqual(searchReducer(state, { type: "error", generation: first, message: "Old error" }), state);
  const cleared = searchReducer(state, { type: "query", query: "" });
  assert.equal(cleared.items.length, 0);
  assert.strictEqual(searchReducer(cleared, { type: "results", generation: second, result: { items: [repository], incomplete: false } }), cleared);
});
check("minimum query, exact URL lookup and bounded result list", () => {
  assert.equal(searchEndpoint("ab"), null);
  assert.equal(searchEndpoint("offline editor"), "/api/community/repositories?q=offline%20editor");
  assert.equal(searchEndpoint("https://github.com/example/editor.git/"), "/api/community/repository?url=https%3A%2F%2Fgithub.com%2Fexample%2Feditor");
  assert.throws(() => searchEndpoint("https://github.com.evil.test/example/editor"));
  assert.throws(() => searchEndpoint("https://github.com/example/editor/issues"));
  assert.throws(() => searchEndpoint("https://token@github.com/example/editor"));
  const state = searchReducer(initialSearchState, { type: "results", generation: 0, result: { items: Array(12).fill(repository), incomplete: false } });
  assert.equal(state.items.length, 10);
});
check("selection fills canonical URL and a usable short repository name", () => {
  assert.deepEqual(repositorySelection(repository), { name: "editor", repoUrl: "https://github.com/example/editor" });
  assert.deepEqual(repositorySelection({ ...repository, name: "x", repoUrl: "https://github.com/example/x" }), { name: "example/x", repoUrl: "https://github.com/example/x" });
  const state = requestReducer(initialRequestState("My idea"), { type: "select", repository });
  assert.equal(state.name, "editor");
  assert.equal(state.repoUrl, "https://github.com/example/editor");
});
check("recorded, duplicate, listed, pending and reviewed responses stay distinct", () => {
  const message = status => submissionMessage({ ok: true, status, suggestionCount: 2 }, true);
  assert.match(message("recorded"), /weekly top ten/i);
  assert.match(message("recorded"), /2 browser suggestions/i);
  assert.match(message("already_suggested"), /already suggested/i);
  assert.match(message("already_listed"), /already listed/i);
  assert.match(message("awaiting_review"), /awaiting.*owner review/i);
  assert.match(message("already_reviewed"), /already reviewed/i);
  assert.doesNotMatch(message("already_reviewed"), /weekly top ten/i);
  assert.match(submissionMessage({ ok: true, status: "recorded", suggestionCount: null }, false), /manual review/i);
  assert.match(submissionMessage({ ok: true }, true), /owner review/i);
});
check("submission and provider errors preserve manual inputs and permit retry", () => {
  let state = requestReducer(initialRequestState("Offline editor"), { type: "edit", field: "repoUrl", value: repository.repoUrl });
  state = requestReducer(state, { type: "start" });
  state = requestReducer(state, { type: "error", message: "Please wait before retrying." });
  assert.equal(state.name, "Offline editor");
  assert.equal(state.repoUrl, repository.repoUrl);
  assert.equal(state.busy, false);
  assert.equal(state.success, false);
  for (const status of [429, 503, 404]) assert.match(searchErrorMessage(status, "12"), /manually|idea/i);
  assert.match(searchErrorMessage(429, "12"), /12 seconds/i);
  state = requestReducer(state, { type: "success", response: { ok: true, status: "recorded", suggestionCount: 1 } });
  assert.equal(state.success, true);
  assert.match(state.message, /1 browser suggestion\b/i);
});
console.log(`${checks} community UI checks passed.`);

// Isolated, reproducible fixture service; no env files, DB or live provider calls.
if (process.argv[2] === "--serve-fixtures") {
  const { createServer } = await import("node:http");
  const { spawn } = await import("node:child_process");
  const server = createServer(async (request, response) => {
    const url = new URL(request.url, "http://127.0.0.1:3184");
    const send = (status, body, headers = {}) => {
      response.writeHead(status, { "Content-Type": "application/json", ...headers });
      response.end(JSON.stringify(body));
    };
    if (url.pathname === "/api/auth/status") return send(200, { owner: true, configured: true });
    if (url.pathname === "/api/config") return send(200, { donationUrl: "", downloadsPaused: false });
    if (url.pathname === "/api/admin/dashboard") return send(200, {
      settings: {}, apps: [], candidates: [], categories: [], usage: { total: 0, budget: 0 }, requests: [],
      ...(!request.headers.cookie?.includes("fixture_legacy=1") && { communitySuggestions: [{
        repoId: repository.repoId, repoUrl: repository.repoUrl, name: repository.name,
        suggestionCount: 2, state: "pending", createdAt: "2026-10-12T00:00:00.000Z",
      }] }),
    });
    if (url.pathname === "/api/community/repositories") {
      const query = url.searchParams.get("q");
      if (query === "busy") return send(429, { error: "Throttled" }, { "Retry-After": "12" });
      if (query === "unavailable") return send(503, { error: "Unavailable" });
      return send(200, { items: query === "empty" ? [] : [repository], incomplete: query === "partial" });
    }
    if (url.pathname === "/api/community/repository") return send(200, { item: repository });
    if (url.pathname === "/api/requests" && request.method === "POST") {
      let body = ""; for await (const chunk of request) body += chunk;
      const data = JSON.parse(body);
      return send(201, { ok: true, status: "recorded", suggestionCount: data.repoUrl ? 2 : null });
    }
    send(404, { error: "Fixture endpoint not configured" });
  });
  server.listen(3184, "127.0.0.1", () => {
    const child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--webpack", "--hostname", "127.0.0.1", "--port", "3183"], {
      cwd: new URL("..", import.meta.url), stdio: "inherit",
      env: { PATH: "/opt/homebrew/bin:/usr/bin:/bin", NODE_ENV: "development", NEXT_TELEMETRY_DISABLED: "1", BACKEND_URL: "http://127.0.0.1:3184", BACKEND_PROXY_SECRET: "synthetic-fixture-proxy-only" },
    });
    const stop = () => { child.kill("SIGTERM"); server.close(); };
    process.on("SIGINT", stop); process.on("SIGTERM", stop);
    child.on("exit", () => server.close());
  });
}

// Optional render smoke against an isolated Next server with a synthetic backend.
// Never point this at the shared local service or production.
if (process.argv[2] === "--http") {
  const base = new URL(process.argv[3]);
  assert.ok(["127.0.0.1", "localhost"].includes(base.hostname), "Fixture smoke must use localhost");
  for (const [path, expected] of [
    ["/request?name=Offline%20editor", ["Find a public GitHub project", 'value="Offline editor"', 'name="repoUrl"', 'name="website"', 'role="status"', "weekly", "180 days"]],
    ["/admin?tab=requests", ["Weekly community suggestions", "browser suggestions", "Pending weekly selection", "Ideas and earlier app requests"]],
    ["/about", ['id="privacy"', "HttpOnly", "pseudonymous", "GitHub"]],
  ]) {
    const response = await fetch(new URL(path, base));
    assert.equal(response.status, 200, path);
    const html = (await response.text()).replace(/<!--[\s\S]*?-->/g, "");
    for (const word of expected) assert.ok(html.includes(word), `${path}: ${word}`);
    console.log(`PASS HTTP rendered fixture ${path}`);
  }
  const legacy = await fetch(new URL("/admin?tab=requests", base), { headers: { Cookie: "fixture_legacy=1" } });
  assert.equal(legacy.status, 200);
  assert.ok((await legacy.text()).includes("No community repository suggestions yet."));
  console.log("PASS HTTP admin rollout without communitySuggestions");
}
