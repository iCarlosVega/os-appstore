import { backendRequest } from "./backend";
export async function ownerStatus() { return backendRequest<{ owner: boolean; configured: boolean }>("/api/auth/status"); }
