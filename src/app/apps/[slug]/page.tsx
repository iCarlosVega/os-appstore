import { Suspense } from "react";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { getApp, getSettings, categories } from "@/lib/store";
import { DownloadMenu } from "@/components/download-menu";
import { AppIcon } from "@/components/app-icon";
import { AppReadme } from "@/components/app-readme";

export const dynamic = "force-dynamic";

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const app = await getApp(slug);
  if (!app) notFound();
  if ("redirect" in app) permanentRedirect(`/apps/${app.redirect}`);
  const [settings, cats] = await Promise.all([getSettings(), categories()]);
  const fallback = "Not provided";

  return <article className="detail">
    <Link href="/">← All software</Link>
    <div className="detail-header">
      <div className="detail-heading">
        <AppIcon repoId={app.repoId} name={app.name} large />
        <div><h1>{app.name}</h1><p>By <a href={app.creatorUrl} rel="noopener noreferrer">{app.creator}</a></p></div>
      </div>
      <DownloadMenu id={app.id} name={app.name} repoUrl={app.repoUrl} disabled={settings.downloadsPaused || !app.downloadsEnabled} />
    </div>
    <p className="intro">{app.description || fallback}</p>
    <div>{app.categories.map(c => <Link className="badge" key={c} href={`/?category=${c}`}>{cats.find(x => x.id === c)?.name || c}</Link>)}</div>
    {app.condition !== "active" && <p className="notice">{app.condition === "inactive" ? "This project has limited recent activity. It remains available in the catalog." : "Repository availability needs review. The last approved project link is shown below."}</p>}
    <Suspense fallback={<section className="app-about"><h2>About this app</h2><p className="muted">Loading README…</p></section>}>
      <AppReadme repoUrl={app.repoUrl} description={app.description} />
    </Suspense>
    <h2>Information</h2>
    <dl>
      <dt>Latest stable version</dt><dd>{app.version || fallback}</dd>
      <dt>Platforms</dt><dd>{app.platforms.join(", ") || fallback}</dd>
      <dt>Architecture</dt><dd>{app.architectures.join(", ") || fallback}</dd>
      <dt>Requirements</dt><dd>{app.requirements || fallback}</dd>
      <dt>Setup</dt><dd>{app.setup}</dd>
      <dt>License</dt><dd>{app.license || fallback}</dd>
      <dt>Cost</dt><dd>{app.costModel}</dd>
      <dt>Download clicks</dt><dd>{app.clicks.toLocaleString()}</dd>
      <dt>Last checked</dt><dd>{app.lastChecked ? new Date(app.lastChecked).toLocaleDateString("en-US", { timeZone: "UTC" }) : fallback}</dd>
    </dl>
    <h2>Official links</h2>
    <ul><li><a href={app.repoUrl}>Source repository</a></li>{Object.entries(app.links).map(([label, url]) => <li key={label}><a href={url} rel="noopener noreferrer">{label}</a></li>)}</ul>
    <h2>Information sources</h2>
    <ul>{(app.sources.length ? app.sources : [app.repoUrl]).map(url => <li className="break" key={url}><a href={url}>{url}</a></li>)}</ul>
    <p className="muted">Download clicks count activations of this store's download button.</p>
  </article>;
}
