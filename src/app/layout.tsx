import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
export const metadata: Metadata = { title: { default: "Free Software Store", template: "%s · Free Software Store" }, description: "Find useful free software, credited to its developers. Browse categories and discover alternatives to paid apps." };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><a className="skip" href="#main">Skip to content</a><header className="site-header"><Link className="brand" href="/"><span className="brand-mark" aria-hidden="true">◈</span> Free Software Store</Link><nav aria-label="Main navigation"><Link href="/">Directory</Link><Link href="/about">About</Link><Link className="nav-submit" href="/request">Submit a project <span aria-hidden="true">↗</span></Link></nav></header><main id="main">{children}</main><footer><span>A community catalog. Every developer credited.</span><Link href="/admin">Administration</Link></footer></body></html>;
}
