"use client";

import { useEffect, useReducer, useRef } from "react";
import { initialSearchState, repositoryStatusLabels, searchEndpoint, searchErrorMessage, searchReducer } from "@/lib/community-types";
import type { RepositoryLookupResult, RepositoryResult, RepositorySearchResult } from "@/lib/community-types";

export function RepositoryPicker({ onSelect, disabled }: { onSelect: (repository: RepositoryResult) => void; disabled: boolean }) {
  const [state, dispatch] = useReducer(searchReducer, initialSearchState);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const { query, generation } = state;
    if (disabled || query.trim().length < 3) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const endpoint = searchEndpoint(query);
        if (!endpoint) return;
        dispatch({ type: "loading", generation });
        const response = await fetch(endpoint, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) {
          dispatch({ type: "error", generation, message: searchErrorMessage(response.status, response.headers.get("Retry-After")) });
          return;
        }
        const data: RepositorySearchResult | RepositoryLookupResult = await response.json();
        const result = "item" in data ? { items: [data.item], incomplete: false } : data;
        dispatch({ type: "results", generation, result });
      } catch (error) {
        if (!controller.signal.aborted) dispatch({ type: "error", generation, message: error instanceof Error && error.message.startsWith("Use a public GitHub") ? `${error.message} You can still submit an idea below.` : searchErrorMessage(503) });
      }
    }, 400);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [state.query, state.generation, disabled]);

  let announcement = "Enter at least three characters. Search is optional; manual fields are below.";
  if (state.phase === "waiting") announcement = "Waiting for you to finish typing…";
  if (state.phase === "loading") announcement = "Searching public GitHub repositories…";
  if (state.phase === "error") announcement = state.message;
  if (state.phase === "ready") announcement = `${state.items.length ? `${state.items.length} result${state.items.length === 1 ? "" : "s"}. Select a project to fill the fields below.` : "No matching repositories. Try other words, paste a URL, or submit an idea below."}${state.incomplete ? " GitHub returned incomplete results; some matches may be missing." : ""}`;

  return <section className="repository-picker" aria-label="Find a GitHub project">
    <label htmlFor="repository-search">Find a public GitHub project</label>
    <input ref={input} id="repository-search" type="search" maxLength={200} autoComplete="off" disabled={disabled}
      value={state.query} onChange={e => dispatch({ type: "query", query: e.target.value })}
      onKeyDown={e => { if (e.key === "Enter") e.preventDefault(); }}
      aria-describedby="repository-search-help repository-search-status" aria-controls="repository-results"
      placeholder="Project name, description, owner/repo or GitHub URL" />
    <p id="repository-search-help" className="muted">GitHub best matches, up to ten results. Stars describe the project and do not determine weekly selection.</p>
    <p id="repository-search-status" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    <ul id="repository-results" className="repository-results" aria-label="GitHub search results" aria-busy={state.phase === "loading"}>
      {state.items.map(repository => <li key={repository.repoId} className="repository-result">
        <h3>{repository.owner}/{repository.name}</h3>
        <p>{repository.description || "No description provided."}</p>
        <p className="muted">{repository.stars.toLocaleString()} stars · License: {repository.license || "Not provided"}</p>
        <p><span className="badge">{repositoryStatusLabels[repository.status]}</span>{repository.archived && <span className="badge">Archived</span>}</p>
        <div className="repository-actions"><button type="button" className="secondary" disabled={disabled} onClick={() => {
          onSelect(repository);
          dispatch({ type: "query", query: "" });
          input.current?.focus();
        }}>Select {repository.owner}/{repository.name}</button>
          <a href={repository.repoUrl} target="_blank" rel="noopener noreferrer">Official repository <span className="muted">(new tab)</span></a></div>
      </li>)}
    </ul>
  </section>;
}
