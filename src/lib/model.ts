import { z } from "zod";

export const JOB_KINDS = ["discovery", "maintenance", "priority", "digest", "backup", "community"] as const;
export const CATEGORY_NAMES = ["Productivity", "Development", "Creative Tools", "Privacy", "Utilities", "Communication", "Education", "AI", "Gaming"];
export const PLATFORMS = ["Windows", "macOS", "Linux", "Android", "iOS", "Browser"] as const;
export const TYPES = ["Desktop app", "Mobile app", "Game", "Command-line tool", "Browser extension", "Plugin", "Library", "Self-hosted service", "Web app"] as const;
export const slugify = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);
const short = z.string().trim().max(200);
const https = z.string().url().refine(s => {
  try { return new URL(s).protocol === "https:"; } catch { return false; }
}, "Use an HTTPS URL");
export const Metadata = z.object({
  repoId: z.string().regex(/^\d+$/), repoUrl: https, name: short.min(1), creator: short.min(1), creatorUrl: https,
  description: z.string().trim().max(4000).default(""), license: short.default(""), version: short.default(""),
  platforms: z.array(z.enum(PLATFORMS)).max(6).default([]), architectures: z.array(z.enum(["x86-64", "ARM64"])).default([]),
  categories: z.array(z.string().max(80)).max(20).default([]), tags: z.array(short).max(30).default([]), aliases: z.array(short).max(30).default([]), alternatives: z.array(short).max(30).default([]),
  requirements: z.string().max(4000).default(""), type: z.enum(TYPES).default("Desktop app"),
  setup: short.default("See project instructions"), costModel: z.enum(["Free", "Free with optional paid features", "Needs review"]).default("Needs review"),
  attributes: z.object({ offline: z.boolean().nullable(), noAccount: z.boolean().nullable(), accessible: z.boolean().nullable(), lightweight: z.boolean().nullable() }).default({ offline: null, noAccount: null, accessible: null, lightweight: null }),
  links: z.record(z.string().max(40), https).default({}), sources: z.array(https).max(20).default([]),
  stars: z.number().int().nonnegative().default(0), archived: z.boolean().default(false), lastActivity: short.default(""),
  lastChecked: short.default(""), condition: z.enum(["active", "inactive", "availability-needs-review"]).default("active"),
  priority: z.boolean().default(false), downloadsEnabled: z.boolean().default(true), nsfw: z.boolean().default(false),
  overrides: z.array(z.string().max(40)).default([])
});
export type Metadata = z.infer<typeof Metadata>;
export type App = Metadata & { id: string; slug: string; revision: number; published: boolean; clicks: number };
export type Candidate = { repoId: string; revision: number; status: string; data: Metadata; assessment: Record<string, unknown>; updatedAt: string };
export type Category = { id: string; name: string; parent_id: string | null };
const clock = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/);
export const Settings = z.object({
  revision: z.number().int().default(1), budgetMicros: z.number().int().min(1).max(20000000).default(20000000),
  hostingMicros: z.number().int().nonnegative().nullable().default(null), hostingActualMicros: z.number().int().nonnegative().default(0),
  hostingActualPeriod: z.string().regex(/^$|^\d{4}-\d{2}$/).default(""),
  jevMicrosPerMillion: z.number().int().positive().nullable().default(null),
  discoveryPaused: z.boolean().default(false), maintenancePaused: z.boolean().default(false), publicationPaused: z.boolean().default(false), downloadsPaused: z.boolean().default(false), aiPaused: z.boolean().default(true), budgetPaused: z.boolean().default(false),
  failedKinds: z.array(z.string()).default([]), timezone: z.string().default("America/New_York").refine(t => { try { new Intl.DateTimeFormat("en", { timeZone: t }); return true; } catch { return false; } }),
  discoveryTime: clock.default("02:00"), maintenanceTime: clock.default("03:00"), priorityTime: clock.default("03:00"), digestTime: clock.default("09:00"), backupTime: clock.default("03:30"),
  dailyCandidates: z.number().int().min(1).max(100).default(10), repositoryLimit: z.number().int().min(1).max(100).default(100),
  seeds: z.array(z.string().max(300)).max(100).default([]), donationUrl: z.union([https, z.literal("")]).default("")
});
export type Settings = z.infer<typeof Settings>;
