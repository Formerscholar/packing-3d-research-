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

export async function downloadPackingList(
  req: PackRequest,
  format: "xlsx" | "csv" = "xlsx"
): Promise<void> {
  const r = await fetch(`${BASE}/api/pack/export?format=${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`export failed: ${r.status} ${t}`);
  }
  const blob = await r.blob();
  const header = r.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  const plain = /filename="([^"]+)"/i.exec(header);
  const filename = star
    ? decodeURIComponent(star[1])
    : plain?.[1] ?? `packing-list.${format}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
