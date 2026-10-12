import { Catalog } from "@/components/catalog";
import { categories } from "@/lib/store";
import { searchCatalog } from "@/lib/search";
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q.slice(0, 200) : "";
  const filters = Object.fromEntries(["category", "platform", "type", "attribute"].map(key => [key, typeof params[key] === "string" ? params[key].slice(0, 200) : ""]));
  const [initial, cats] = await Promise.all([searchCatalog(q, filters, false), categories()]);
  return <Catalog key={JSON.stringify({ q, filters })} initial={initial} categories={cats} initialQuery={q} initialFilters={filters} />;
}
