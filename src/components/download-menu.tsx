"use client";

import { useEffect, useRef, useState } from "react";

export function DownloadMenu({ id, name, repoUrl, disabled }: { id: string; name: string; repoUrl: string; disabled: boolean }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [copied, setCopied] = useState(false);
  const [manualCopy, setManualCopy] = useState(false);
  const options = useRef<HTMLDetailsElement>(null);
  const prompt = `Download and install ${name} on my device using its official repository: ${repoUrl}. Follow the project's README and official installation instructions for my operating system.`;

  useEffect(() => {
    function dismiss(event: PointerEvent) {
      if (options.current && !options.current.contains(event.target as Node)) options.current.open = false;
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape" && options.current?.open) {
        options.current.open = false;
        options.current.querySelector("summary")?.focus();
      }
    }
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
    };
  }, []);

  async function download() {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/download", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      window.location.assign(data.url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not open the project.");
      setBusy(false);
    }
  }

  async function copyForAI() {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setManualCopy(false);
      setMessage("Copied. Paste into your AI assistant to get installation help.");
    } catch {
      setManualCopy(true);
      setMessage("Select and copy the prompt below.");
      if (options.current) options.current.open = false;
    }
  }

  return <div className="panel download-panel">
    <div className="download-row">
      <div className="download-split">
        <button className="download-primary" disabled={disabled || busy} onClick={() => void download()}>
          {disabled ? "Downloads paused" : busy ? "Opening…" : "Download"}
          <span aria-hidden="true">↗</span>
        </button>
        <details className="download-options" ref={options}>
          <summary className="download-toggle">
            <span className="sr-only">More download options</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </summary>
          <div className="download-dropdown">
            <span className="download-dropdown-label">INSTALL WITH YOUR ASSISTANT</span>
            <button className="copy-ai-option" onClick={() => void copyForAI()}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
                {copied ? <path d="m5 12 4 4L19 6" /> : <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>}
              </svg>
              <span><strong>{copied ? "Copied!" : "Copy for AI"}</strong><small>Get help installing this app</small></span>
            </button>
          </div>
        </details>
      </div>
      <span className="muted">Opens the official GitHub repository</span>
    </div>
    <p className="muted download-note">Download at your own risk.</p>
    <p className="download-status" role="status">{message}</p>
    {manualCopy && <label className="manual-copy">Installation prompt<textarea autoFocus readOnly value={prompt} onFocus={event => event.currentTarget.select()} /></label>}
  </div>;
}
