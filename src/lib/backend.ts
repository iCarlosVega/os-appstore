import { cookies, headers } from "next/headers";
import type { App, Candidate, Category, Settings } from "./model";

export const backendUrl = () => (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export class BackendError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export async function backendRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const incoming = await headers();
  const requestHeaders = new Headers(options.headers);
  requestHeaders.set("Cookie", (await cookies()).toString());
  if (process.env.BACKEND_PROXY_SECRET) requestHeaders.set("X-Store-Proxy", process.env.BACKEND_PROXY_SECRET);
  const address = incoming.get("x-forwarded-for");
  if (address) requestHeaders.set("X-Forwarded-For", address);
  let response: Response;
  try {
    response = await fetch(`${backendUrl()}${path}`, { ...options, headers: requestHeaders, cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(15000) });
  } catch { throw new BackendError("The FastAPI backend is unavailable. Start the backend service and check BACKEND_URL.", 503); }
  if (response.status === 404) throw new BackendError("This listing is unavailable.", 404);
  const data = await response.json();
  if (!response.ok) throw new BackendError(typeof data.error === "string" ? data.error : "The backend request could not be completed.", response.status);
  return data as T;
}
export type SearchResult = { items: App[]; related: boolean; mode: string; total: number };
export type Dashboard = {
  settings: Settings; apps: App[]; candidates: Candidate[]; categories: Category[];
  usage: { period: string; ai: number; hosting: number; total: number; budget: number; configured: boolean };
  proposals: Record<string, unknown>[]; requests: Record<string, unknown>[]; jobs: Record<string, unknown>[];
  notifications: Record<string, unknown>[]; costEntries: Record<string, unknown>[];
  communitySuggestions?: import("./community-types").CommunitySuggestion[];
};
