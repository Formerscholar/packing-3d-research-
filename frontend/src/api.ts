import type { PackRequest, PackResponse } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export async function fetchSample(): Promise<PackRequest> {
  const r = await fetch(`${BASE}/api/sample`);
  if (!r.ok) throw new Error(`sample failed: ${r.status}`);
  return r.json();
}

export async function pack(req: PackRequest): Promise<PackResponse> {
  const r = await fetch(`${BASE}/api/pack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`pack failed: ${r.status} ${t}`);
  }
  return r.json();
}
