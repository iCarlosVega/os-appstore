"use server";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { backendRequest } from "@/lib/backend";

export async function adminAction(form: FormData) {
  const tabs = ["candidates", "listings", "changes", "requests", "categories", "operations", "settings", "costs"];
  const selected = String(form.get("tab") || "");
  const tab = tabs.includes(selected) ? selected : "overview";
  const fields: Record<string, string[]> = {};
  for (const [key, value] of form) {
    if (typeof value !== "string") throw new Error("File uploads are not accepted.");
    (fields[key] ??= []).push(value);
  }
  let message: string;
  try {
    const result = await backendRequest<{ message: string }>("/api/admin/actions", {
      method: "POST", headers: { "Content-Type": "application/json", Origin: (await headers()).get("origin") || "" },
      body: JSON.stringify({ operation: String(form.get("operation") || ""), fields })
    });
    message = result.message;
  } catch (error) {
    redirect(`/admin?tab=${tab}&error=${encodeURIComponent(error instanceof Error ? error.message.slice(0, 500) : "The request could not be completed.")}`);
  }
  redirect(`/admin?tab=${tab}&message=${encodeURIComponent(message)}`);
}
