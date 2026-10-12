"use client";
import { useState } from "react";
export function DownloadMenu({ id, name, repoUrl, disabled }: { id: string; name: string; repoUrl: string; disabled: boolean }) {
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  async function download() { setBusy(true); setMessage(""); try { const r = await fetch("/api/download", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }); const data = await r.json(); if (!r.ok) throw new Error(data.error); window.location.assign(data.url); } catch (e) { setMessage(e instanceof Error ? e.message : "Could not open the project."); setBusy(false); } }
  const prompt = `Download and install ${name} on my device using its official repository: ${repoUrl}.`;
  return <div className="panel"><button disabled={disabled || busy} onClick={() => void download()}>{disabled ? "Downloads paused" : busy ? "Opening…" : "Download ↗"}</button><span className="muted"> Opens the official GitHub repository</span><details><summary>More download options</summary><p>Copy this prompt into your preferred assistant:</p><pre>{prompt}</pre><button className="secondary" onClick={async () => { try { await navigator.clipboard.writeText(prompt); setMessage("Install prompt copied."); } catch { setMessage("Select and copy the prompt above."); } }}>Copy install prompt</button></details><p className="muted">Download at your own risk.</p><p role="status">{message}</p></div>;
}
