"""FastAPI entry: pack endpoint + CORS for Vite localhost."""

from __future__ import annotations

from typing import List
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .engine import LayoutError, evaluate_layout, pack
from .export import to_csv, to_pdf, to_xlsx
from .import_sku import parse_sku_workbook
from .models import ContainerIn, ItemIn, PackRequest, PackResponse

app = FastAPI(
    title="Packing 3D Research API",
    description="Compact packer with load-bearing, COG, LIFO",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_ITEMS = [
    ItemIn(
        id="SKU-A",
        name="纸箱A 600x400x400",
        length=600,
        width=400,
        height=400,
        weight=12,
        qty=24,
        max_stack_load_kg=60,
    ),
    ItemIn(
        id="SKU-B",
        name="纸箱B 800x600x500",
        length=800,
        width=600,
        height=500,
        weight=25,
        qty=12,
        max_stack_load_kg=80,
    ),
    ItemIn(
        id="SKU-C",
        name="纸箱C 400x300x300",
        length=400,
        width=300,
        height=300,
        weight=8,
        qty=30,
        max_stack_load_kg=40,
    ),
]


@app.get("/api/health")
def health():
    return {"ok": True, "service": "packing-3d"}


@app.get("/api/sample")
def sample() -> PackRequest:
    return PackRequest(container=ContainerIn(), items=SAMPLE_ITEMS)


def _solve(req: PackRequest) -> PackResponse:
    if req.placements is not None:
        try:
            return evaluate_layout(req.container, req.items, req.placements)
        except LayoutError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return pack(req.container, req.items)


@app.post("/api/pack", response_model=PackResponse)
def pack_endpoint(req: PackRequest) -> PackResponse:
    return pack(req.container, req.items)


@app.post("/api/pack/layout", response_model=PackResponse)
def layout_endpoint(req: PackRequest) -> PackResponse:
    if req.placements is None:
        raise HTTPException(status_code=400, detail="placements required")
    return _solve(req)


@app.post("/api/items/import")
async def import_items(file: UploadFile = File(...)) -> dict:
    """Parse an Excel/CSV SKU list into ItemIn rows."""
    name = (file.filename or "").lower()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        items: List[ItemIn] = parse_sku_workbook(raw, name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"parse failed: {e}") from e
    if not items:
        raise HTTPException(status_code=400, detail="no SKU rows found")
    return {"items": [it.model_dump() for it in items], "count": len(items)}


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
    format: str = Query("xlsx", description="xlsx, csv, or pdf"),
) -> Response:
    fmt = format.lower()
    result = _solve(req)
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
    if fmt == "pdf":
        try:
            payload = to_pdf(req, result)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return Response(
            content=payload,
            media_type="application/pdf",
            headers=_attachment(req.container.name, "pdf"),
        )
    raise HTTPException(status_code=400, detail="format must be xlsx, csv, or pdf")
