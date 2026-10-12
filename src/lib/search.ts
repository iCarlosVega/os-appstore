import { backendRequest, SearchResult } from "./backend";
export type Filters = { category?: string; platform?: string; type?: string; attribute?: string };
export async function searchCatalog(query: string, filters: Filters = {}, useAI = true) {
  const params = new URLSearchParams({ q: query, ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== undefined)) as Record<string, string>, use_ai: String(useAI) });
  return backendRequest<SearchResult>(`/api/search?${params}`);
}
