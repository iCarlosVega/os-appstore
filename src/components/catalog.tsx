"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { AppCard } from "./app-card";
import { App, Category, PLATFORMS, TYPES } from "@/lib/model";
import type { Filters } from "@/lib/search";

type Result = { items: App[]; related: boolean; mode: string; total: number };
export function Catalog({ initial, categories, initialQuery = "", initialFilters = {} }: { initial: Result; categories: Category[]; initialQuery?: string; initialFilters?: Filters }) {
  const [result, setResult] = useState(initial);
  const [query, setQuery] = useState(initialQuery);
  const [filters, setFilters] = useState(initialFilters);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  async function search(next = filters) {
    const id = ++requestId.current;
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({ q: query, ...next });
      const response = await fetch(`/api/search?${params}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Search is unavailable. Please try again.");
      if (id !== requestId.current) return;
      setResult(data); window.history.replaceState(null, "", `/?${params}`);
    } catch (e) { if (id === requestId.current) setError(e instanceof Error ? e.message : "Search failed."); }
    finally { if (id === requestId.current) setBusy(false); }
  }
  function change(key: keyof Filters, value: string) {
    const next = { ...filters, [key]: value };
    setFilters(next); void search(next);
  }
  const active = Object.values(filters).filter(Boolean).length;
  return <div className="directory">
    <aside className="filter-sidebar" aria-label="Filter software">
      <div className="row between filter-title"><h2>Filters</h2>{active > 0 && <button className="text-button" onClick={() => { setFilters({}); void search({}); }}>Clear {active}</button>}</div>
      <details open className="filter-group"><summary>Categories</summary><nav className="categories" aria-label="Categories">
        <a href="/" aria-current={!filters.category ? "page" : undefined} className={!filters.category ? "selected" : ""} onClick={e => { e.preventDefault(); change("category", ""); }}><span>All software</span><span aria-hidden="true">↗</span></a>
        {categories.map(c => <a key={c.id} href={`/?category=${c.id}`} aria-current={filters.category === c.id ? "page" : undefined} className={filters.category === c.id ? "selected" : ""} style={{ paddingLeft: c.parent_id ? "1.5rem" : undefined }} onClick={e => { e.preventDefault(); change("category", c.id); }}>{c.name}</a>)}
      </nav></details>
      <details open className="filter-group"><summary>Platform</summary><div className="filter-options"><label className="sr-only" htmlFor="platform">Platform</label><select id="platform" value={filters.platform || ""} onChange={e => change("platform", e.target.value)}><option value="">All platforms</option>{PLATFORMS.map(p => <option key={p}>{p}</option>)}</select></div></details>
      <details open className="filter-group"><summary>Software type</summary><div className="filter-options"><label className="sr-only" htmlFor="type">Software type</label><select id="type" value={filters.type || ""} onChange={e => change("type", e.target.value)}><option value="">All types</option>{TYPES.map(t => <option key={t}>{t}</option>)}</select></div></details>
      <details open className="filter-group"><summary>Features</summary><div className="filter-options"><label className="sr-only" htmlFor="attribute">Features</label><select id="attribute" value={filters.attribute || ""} onChange={e => change("attribute", e.target.value)}><option value="">Any features</option><option value="offline">Works offline</option><option value="noAccount">No account required</option><option value="accessible">Accessibility features</option><option value="lightweight">Low hardware requirements</option></select></div></details>
      <div className="sidebar-note"><p>Made by developers.<br />Collected for everyone.</p><Link href="/about">About this project <span aria-hidden="true">↗</span></Link></div>
    </aside>
    <section className="directory-content" aria-label="Software directory">
      <div className="directory-heading"><span className="eyebrow">THE FREE SOFTWARE DIRECTORY</span><h1>Find your next favorite app.</h1><p>Useful apps, games, and open source alternatives. Free to use, with every developer credited.</p></div>
      <form className="searchbar" onSubmit={e => { e.preventDefault(); void search(); }}><label className="sr-only" htmlFor="search">Search software</label><span className="search-icon" aria-hidden="true">⌕</span><input id="search" type="search" maxLength={200} placeholder="Search apps, games, or alternatives…" value={query} onChange={e => setQuery(e.target.value)} /><button disabled={busy}>{busy ? "Searching…" : "Search"}</button></form>
      {error && <p role="alert" className="notice error">{error}</p>}
      <div className="row between results-heading"><h2>{filters.category ? categories.find(c => c.id === filters.category)?.name || "Software" : query ? "Search results" : "All software"}<span className="count">{result.total}</span></h2><Link href={`/request?name=${encodeURIComponent(query)}`}>Request an app <span aria-hidden="true">↗</span></Link></div>
      {result.related && <p className="muted">No exact match. Here are some related apps to explore.</p>}
      <div aria-live="polite" aria-busy={busy}>
        {result.items.length ? <div className="grid">{result.items.map(app => <AppCard key={app.id} app={app} />)}</div> : <div className="empty"><span className="empty-icon" aria-hidden="true">＋</span><h2>{!query && !active ? "Good software starts with a suggestion." : "No apps match just yet."}</h2><p>{!query && !active ? "The first collection is on its way. Have a project you love? Send it in for review." : "Try a different search or fewer filters. You can also ask us to add a project."}</p><Link className="button secondary" href={`/request?name=${encodeURIComponent(query)}`}>Suggest an app <span aria-hidden="true">↗</span></Link></div>}
      </div>
      <p className="directory-footnote">Downloads open the official project repository. Download at your own risk.</p>
    </section>
  </div>;
}
