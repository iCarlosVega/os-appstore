"use client";
import { useReducer } from "react";
import { RepositoryPicker } from "@/components/repository-picker";
import { initialRequestState, requestReducer } from "@/lib/community-types";
import type { SubmissionResponse } from "@/lib/community-types";
export function RequestForm({ initialName }: { initialName: string }) {
  const [state, dispatch] = useReducer(requestReducer, initialName, initialRequestState);
  return <form className="panel request-form" onSubmit={async e => {
    e.preventDefault();
    if (state.busy || state.success) return;
    const data = new FormData(e.currentTarget);
    dispatch({ type: "start" });
    try {
      const response = await fetch("/api/requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(data)) });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : "Your request could not be submitted. Please try again.");
      dispatch({ type: "success", response: result as SubmissionResponse });
    } catch (error) {
      dispatch({ type: "error", message: error instanceof Error ? error.message : "Request failed. Please try again." });
    }
  }}>
    <RepositoryPicker disabled={state.busy || state.success} onSelect={repository => dispatch({ type: "select", repository })} />
    <fieldset className="request-fields" disabled={state.busy || state.success}>
      <legend>Suggest a project or describe an idea</legend>
      <p className="muted">You can recommend your own project. A repository URL is optional for ideas; ideas go to manual review.</p>
      <label>App name or what you need<input name="name" required minLength={2} maxLength={200} value={state.name} onChange={e => dispatch({ type: "edit", field: "name", value: e.target.value })} placeholder="For example, an offline PDF editor" /></label>
      <label>GitHub repository URL (optional)<input name="repoUrl" type="url" maxLength={300} value={state.repoUrl} onChange={e => dispatch({ type: "edit", field: "repoUrl", value: e.target.value })} placeholder="https://github.com/owner/project" /></label>
      <label className="honeypot" aria-hidden="true">Website<input name="website" tabIndex={-1} autoComplete="off" /></label>
    </fieldset>
    <p className="muted">No login or email needed. A signed browser cookie lasts up to 180 days and counts this browser once per project. We store a pseudonymous key and suggestions for owner review, not the raw cookie or IP in contribution records. Browser counts do not prove unique people. Please leave out personal information. <a href="/about#privacy">Privacy details</a></p>
    <button type="submit" disabled={state.busy || state.success}>{state.busy ? "Sending…" : state.success ? "Request received" : "Submit request"}</button>
    <p role="status" aria-live="polite" aria-atomic="true">{state.message}</p>
  </form>;
}
