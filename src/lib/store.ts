import { BackendError, backendRequest } from "./backend";
import type { App, Category, Settings } from "./model";

export async function getSettings() {
  return backendRequest<Pick<Settings, "donationUrl" | "downloadsPaused">>("/api/config");
}
export async function categories() { return backendRequest<Category[]>("/api/categories"); }
export async function getApp(slug: string): Promise<(App | { redirect: string }) | undefined> {
  try { return await backendRequest<App | { redirect: string }>(`/api/apps/${encodeURIComponent(slug)}`); }
  catch (error) { if (error instanceof BackendError && error.status === 404) return; throw error; }
}
