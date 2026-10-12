import { backendUrl } from "@/lib/backend";
export const dynamic = "force-dynamic";

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path.some(part => !/^[a-zA-Z0-9_-]+$/.test(part))) return Response.json({ error: "Invalid API path." }, { status: 400 });
  const url = `${backendUrl()}/api/${path.map(encodeURIComponent).join("/")}${new URL(request.url).search}`;
  const headers = new Headers();
  for (const key of ["cookie", "origin", "content-type", "content-length", "x-forwarded-for"]) {
    const value = request.headers.get(key); if (value) headers.set(key, value);
  }
  if (process.env.BACKEND_PROXY_SECRET) headers.set("X-Store-Proxy", process.env.BACKEND_PROXY_SECRET);
  try {
    const reader = request.body?.getReader(); const chunks: Uint8Array[] = []; let bytes = 0;
    if (reader) try {
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        bytes += value.byteLength;
        if (bytes > 131072) { await reader.cancel(); return Response.json({ error: "Request is too large." }, { status: 413 }); }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
    const response = await fetch(url, { method: request.method, headers, body: chunks.length ? Buffer.concat(chunks) : undefined, redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(25000) });
    const output = new Headers({ "Cache-Control": "no-store" });
    for (const key of ["content-type", "location", "retry-after"]) { const value = response.headers.get(key); if (value) output.set(key, value); }
    for (const cookie of response.headers.getSetCookie()) output.append("Set-Cookie", cookie);
    return new Response(response.body, { status: response.status, headers: output });
  } catch { return Response.json({ error: "The store backend is temporarily unavailable." }, { status: 503 }); }
}
export { proxy as GET, proxy as POST };
