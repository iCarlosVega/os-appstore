import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import { getReadme } from "@/lib/readme";

export async function AppReadme({ repoUrl, description }: { repoUrl: string; description: string }) {
  const readme = await getReadme(repoUrl);

  return <section className="app-about" aria-labelledby="app-about-title">
    <div className="row between about-heading">
      <h2 id="app-about-title">About this app</h2>
      <a className="muted" href={readme?.url || `${repoUrl}#readme`} rel="noopener noreferrer">Read on GitHub ↗</a>
    </div>
    {readme ? <div className="readme">
      {/* Use the img fallback because URL transforms do not resolve picture srcsets. */}
      <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw, rehypeSanitize]} disallowedElements={["source"]}
        urlTransform={(url, key) => {
          const safe = defaultUrlTransform(url);
          if (!safe) return "";
          try { return new URL(safe, key === "src" ? readme.rawUrl : readme.url).href; }
          catch { return ""; }
        }}
        components={{
          a: ({ node, ...props }) => <a {...props} rel="noopener noreferrer" />,
          img: ({ node, ...props }) => <img {...props} loading="lazy" decoding="async" />,
          table: ({ node, ...props }) => <div className="readme-table"><table {...props} /></div>
        }}
      >{readme.markdown}</Markdown>
    </div> : <>
      <p>{description || "See the project's README for features and installation instructions."}</p>
      <p className="muted">The README is currently unavailable here. You can read it on GitHub.</p>
    </>}
  </section>;
}
