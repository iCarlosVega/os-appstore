import { RequestForm } from "@/components/request-form";
import "./request.css";

export default async function Page({ searchParams }: { searchParams: Promise<{ name?: string }> }) {
  const params = await searchParams;
  return <section className="narrow request-page"><h1>Request an app</h1>
    <p>Find a public GitHub project or tell us what you need. Up to ten of the most suggested eligible projects are selected each week for owner review. Suggestions carry forward; only owner approval adds an app to the store.</p>
    <RequestForm initialName={typeof params.name === "string" ? params.name.slice(0, 200) : ""} />
  </section>;
}
