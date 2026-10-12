import Link from "next/link";
import type { App } from "@/lib/model";
import { AppIcon } from "./app-icon";

export function AppCard({ app }: { app: App }) {
  return <article className="card app-card">
    <div className="row between"><AppIcon repoId={app.repoId} name={app.name} /><span className="project-source">github.com <span aria-hidden="true">↗</span></span></div>
    <h2><Link href={`/apps/${app.slug}`}>{app.name}</Link></h2>
    <span className="creator">By {app.creator}</span>
    <p className="app-description">{app.description || "See the project's documentation for details."}</p>
    <div className="meta"><div>{app.platforms.length ? app.platforms.map(p => <span className="badge" key={p}>{p}</span>) : <span className="muted">Platforms not provided</span>}{app.tags.slice(0, 2).map(t => <span className="badge" key={`tag:${t}`}>{t}</span>)}</div>
      {app.condition !== "active" && <span className="badge">{app.condition === "inactive" ? "Inactive project" : "Availability needs review"}</span>}
      <div className="row between card-footer"><span>{app.license || "License not provided"}</span><span>{app.clicks.toLocaleString()} download clicks</span></div>
    </div>
  </article>;
}
