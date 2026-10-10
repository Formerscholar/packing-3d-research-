"""FastAPI entry: pack endpoint + CORS for Vite localhost."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .engine import pack
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
