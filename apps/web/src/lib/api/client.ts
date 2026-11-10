// client.ts - the typed API client.
// `paths` and `components` come from schema.d.ts, which is GENERATED from FastAPI's OpenAPI
// schema (npm run gen:api). Never hand-edit schema.d.ts: change the Python models instead.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "", credentials: "include" });

// Short names for the response types used across the app.
export type S = components["schemas"];
export type User = S["UserOut"];
export type JobSummary = S["JobSummary"];
export type JobDetail = S["JobDetail"];
export type Analytics = S["Analytics"];
export type ThreadSummary = S["ThreadSummary"];
export type ThreadDetail = S["ThreadDetail"];
export type MemoryItem = S["MemoryItem"];
export type Settings = S["Settings"];

/** Turn an openapi-fetch result into data, or throw an Error with the server's message. */
export function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || !res.response.ok) {
    const e = res.error as { detail?: unknown } | undefined;
    const detail = typeof e?.detail === "string" ? e.detail : JSON.stringify(e?.detail ?? res.response.statusText);
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.response.status;
    throw err;
  }
  return res.data as T;
}
