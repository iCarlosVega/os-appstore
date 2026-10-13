export type RepositoryStatus = "available" | "suggested" | "already_listed" | "awaiting_review" | "already_reviewed";
export type RepositorySummary = {
  repoId: string; repoUrl: string; name: string; owner: string; description: string;
  stars: number; license: string; archived: boolean;
};
export type RepositoryResult = RepositorySummary & { status: RepositoryStatus; suggestionCount: number };
export type RepositorySearchResult = { items: RepositoryResult[]; incomplete: boolean };
export type RepositoryLookupResult = { item: RepositoryResult };
export type SubmissionResponse = {
  ok: true;
  status?: "recorded" | "already_suggested" | "already_listed" | "awaiting_review" | "already_reviewed";
  suggestionCount?: number | null;
};
export type CommunitySuggestion = {
  repoId: string; repoUrl: string; name: string; suggestionCount: number;
  state: "pending" | "queued"; createdAt: string;
};
export const repositoryStatusLabels: Record<RepositoryStatus, string> = {
  available: "Available to suggest", suggested: "Suggested for weekly consideration",
  already_listed: "Already listed", awaiting_review: "Awaiting owner review", already_reviewed: "Already reviewed",
};

export function searchEndpoint(input: string): string | null {
  const query = input.trim();
  if (query.length < 3) return null;
  if (/^https?:\/\//i.test(query)) {
    const match = /^https:\/\/github\.com\/([a-z\d][a-z\d-]*)\/([a-z\d_.-]+)\/?$/i.exec(query);
    if (!match) throw new Error("Use a public GitHub repository URL such as https://github.com/owner/project.");
    const name = match[2].replace(/\.git$/i, "");
    if (!name || name === "." || name === "..") throw new Error("Enter a GitHub repository URL.");
    return `/api/community/repository?url=${encodeURIComponent(`https://github.com/${match[1]}/${name}`)}`;
  }
  return `/api/community/repositories?q=${encodeURIComponent(query)}`;
}

type SearchState = {
  query: string; generation: number; phase: "idle" | "waiting" | "loading" | "ready" | "error";
  items: RepositoryResult[]; incomplete: boolean; message: string;
};
type SearchAction = { type: "query"; query: string }
  | { type: "loading"; generation: number }
  | { type: "results"; generation: number; result: RepositorySearchResult }
  | { type: "error"; generation: number; message: string };
export const initialSearchState: SearchState = { query: "", generation: 0, phase: "idle", items: [], incomplete: false, message: "" };
export function searchReducer(state: SearchState, action: SearchAction): SearchState {
  if (action.type === "query") return { ...initialSearchState, query: action.query, generation: state.generation + 1, phase: action.query.trim().length >= 3 ? "waiting" : "idle" };
  // Abort is best effort: a response in flight must also match the query generation.
  if (action.generation !== state.generation) return state;
  if (action.type === "loading") return { ...state, phase: "loading" };
  if (action.type === "error") return { ...state, phase: "error", items: [], message: action.message };
  return { ...state, phase: "ready", items: action.result.items.slice(0, 10), incomplete: action.result.incomplete };
}

export function searchErrorMessage(status: number, retryAfter: string | null = null): string {
  const manual = "You can still enter a repository URL manually or submit an idea below.";
  if (status === 429) {
    const seconds = retryAfter && /^\d+$/.test(retryAfter) ? ` in ${retryAfter} seconds` : " later";
    return `GitHub lookup is busy. Try again${seconds}. ${manual}`;
  }
  if (status === 404) return "No public repository found at that URL. Check the URL or submit an idea below.";
  return `GitHub lookup is temporarily unavailable. Try again later. ${manual}`;
}

export function repositorySelection(repository: RepositoryResult) {
  return { name: repository.name.length < 2 ? `${repository.owner}/${repository.name}` : repository.name, repoUrl: repository.repoUrl };
}

export function submissionMessage(response: SubmissionResponse, hasRepository: boolean): string {
  switch (response.status) {
    case "already_listed": return "This project is already listed in the store. No new weekly suggestion was added.";
    case "awaiting_review": return "This project is already awaiting owner review. It has not been published by this request.";
    case "already_reviewed": return "This project was already reviewed. This request does not reopen it for review.";
    case "already_suggested": return "This browser has already suggested this project. It is counted once for weekly top ten consideration.";
    case "recorded": {
      if (!hasRepository) return "Your idea was recorded for manual review by the store owner.";
      const count = response.suggestionCount;
      return `Suggestion recorded for weekly top ten consideration.${typeof count === "number" ? ` ${count} browser suggestion${count === 1 ? "" : "s"} recorded for this project.` : ""} Only the owner's approval can add an app to the store.`;
    }
    default: return "Your request was received for owner review. An app is only added after approval.";
  }
}

type RequestState = { name: string; repoUrl: string; busy: boolean; success: boolean; message: string };
type RequestAction = { type: "edit"; field: "name" | "repoUrl"; value: string }
  | { type: "select"; repository: RepositoryResult } | { type: "start" }
  | { type: "success"; response: SubmissionResponse } | { type: "error"; message: string };
export const initialRequestState = (name: string): RequestState => ({ name, repoUrl: "", busy: false, success: false, message: "" });
export function requestReducer(state: RequestState, action: RequestAction): RequestState {
  switch (action.type) {
    case "edit": return { ...state, [action.field]: action.value, message: "" };
    case "select": return { ...state, ...repositorySelection(action.repository), message: `Selected ${action.repository.owner}/${action.repository.name}. Review the fields and submit below.` };
    case "start": return { ...state, busy: true, success: false, message: "" };
    case "success": return { ...state, busy: false, success: true, message: submissionMessage(action.response, Boolean(state.repoUrl.trim())) };
    case "error": return { ...state, busy: false, success: false, message: action.message };
  }
}
