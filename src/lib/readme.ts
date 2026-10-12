import "server-only";
import { z } from "zod";

const document = z.object({
  encoding: z.literal("base64"),
  content: z.string().max(1_500_000),
  html_url: z.string().url(),
  download_url: z.string().url(),
  size: z.number().int().min(1).max(1_000_000)
});

export async function getReadme(repoUrl: string) {
  const repository = /^https:\/\/github\.com\/([\w.-]+)\/([\w.-]+)\/?$/.exec(repoUrl);
  if (!repository) return null;
  const [, owner, repo] = repository;
  try {
    const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/readme`, {
      headers: { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
      next: { revalidate: 3600 }, signal: AbortSignal.timeout(8000), redirect: "error"
    });
    if (!response.ok) return null;
    const result = document.safeParse(await response.json());
    if (!result.success) return null;
    const data = result.data;
    // Keep relative links and images within the approved repository's README location.
    const html = new URL(data.html_url);
    const raw = new URL(data.download_url);
    if (html.origin !== "https://github.com" || !html.pathname.toLowerCase().startsWith(`/${owner}/${repo}/blob/`.toLowerCase()) ||
        raw.origin !== "https://raw.githubusercontent.com" || !raw.pathname.toLowerCase().startsWith(`/${owner}/${repo}/`.toLowerCase())) return null;
    const markdown = Buffer.from(data.content, "base64").toString("utf8");
    if (!markdown.trim()) return null;
    return { markdown, url: html.href, rawUrl: raw.href };
  } catch {
    return null;
  }
}
