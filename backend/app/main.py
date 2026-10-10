"""FastAPI entry: pack endpoint + CORS for Vite localhost."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .engine import pack
from .export import to_csv, to_xlsx
from .models import ContainerIn, ItemIn, PackRequest, PackResponse

app = FastAPI(
    title="Packing 3D Research API",
    description="MVP Container Loading packer (Extreme-Point / FFD)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_ITEMS = [
    ItemIn(id="SKU-A", name="纸箱A 600x400x400", length=600, width=400, height=400, weight=12, qty=20),
    ItemIn(id="SKU-B", name="纸箱B 800x600x500", length=800, width=600, height=500, weight=25, qty=8),
    ItemIn(id="SKU-C", name="纸箱C 400x300x300", length=400, width=300, height=300, weight=8, qty=15),
]


@app.get("/api/health")
def health():
    return {"ok": True, "service": "packing-3d"}


@app.get("/api/sample")
def sample() -> PackRequest:
    """Return a demo request: mixed SKUs into a 20GP."""
    return PackRequest(container=ContainerIn(), items=SAMPLE_ITEMS)


@app.post("/api/pack", response_model=PackResponse)
def pack_endpoint(req: PackRequest) -> PackResponse:
    return pack(req.container, req.items)


def _attachment(name: str, ext: str) -> dict[str, str]:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-")
    ascii_name = f"packing-list-{safe}.{ext}" if safe else f"packing-list.{ext}"
    utf_name = quote(f"装箱单-{name}.{ext}")
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf_name}'
        )
    }


@app.post("/api/pack/export")
def export_pack(
    req: PackRequest,
    format: str = Query("xlsx", description="xlsx or csv"),
) -> Response:
    """Pack, then return a packing list. Same body as POST /api/pack."""
    fmt = format.lower()
    result = pack(req.container, req.items)
    if fmt == "xlsx":
        return Response(
            content=to_xlsx(req, result),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=_attachment(req.container.name, "xlsx"),
        )
    if fmt == "csv":
        return Response(
            content=to_csv(req, result),
            media_type="text/csv; charset=utf-8",
            headers=_attachment(req.container.name, "csv"),
        )
    raise HTTPException(status_code=400, detail="format must be xlsx or csv")
