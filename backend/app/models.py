"""Pydantic request/response models for the packing API."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .containers import CATALOG

_GP20 = CATALOG["20GP"]


class ItemIn(BaseModel):
    """One SKU / carton to pack (dimensions in mm, weight in kg)."""

    id: str = Field(..., description="Unique item id, e.g. SKU-001")
    name: Optional[str] = None
    length: float = Field(..., gt=0, description="X axis (mm)")
    width: float = Field(..., gt=0, description="Y axis (mm)")
    height: float = Field(..., gt=0, description="Z axis (mm)")
    weight: float = Field(0.0, ge=0, description="kg")
    qty: int = Field(1, ge=1, description="How many identical pieces")
    allow_rotate: bool = Field(
        True, description="Allow 90° yaw (swap length/width) on XY plane"
    )
    # Max weight that may rest on top of this carton (kg). None = default 5x own weight.
    max_stack_load_kg: Optional[float] = Field(
        None, ge=0, description="承重上限：上方允许堆放的总重量 kg"
    )
    stackable: bool = Field(True, description="是否允许被压在下面承重")
    unload_seq: Optional[int] = Field(
        None,
        ge=1,
        description="卸货次序，1 最先卸，应靠近柜门（长度正方向）",
    )


class ContainerIn(BaseModel):
    """Max enclosure / container inner dims (mm); packer minimizes tight outer box inside this."""

    name: str = _GP20.code
    length: float = Field(_GP20.length, gt=0)
    width: float = Field(_GP20.width, gt=0)
    height: float = Field(_GP20.height, gt=0)
    max_weight: Optional[float] = Field(_GP20.max_weight, description="kg, optional")
    # Soft CG band as fraction of L/W from geometric center (0.15 = ±15%).
    cog_band: float = Field(_GP20.cog_band, ge=0.05, le=0.5)


class PlacementOut(BaseModel):
    id: str
    name: Optional[str] = None
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    weight: float
    rotated: bool = False
    unload_order: int = 0  # 1 = first off (near door)
    load_order: int = 0  # 1 = first on (far from door)


class PackRequest(BaseModel):
    container: ContainerIn = Field(default_factory=ContainerIn)
    items: List[ItemIn]
    # When set, export/layout keeps these poses instead of running a new search.
    placements: Optional[List[PlacementOut]] = None


class PackStats(BaseModel):
    placed_count: int
    unplaced_count: int
    volume_used_m3: float
    volume_total_m3: float
    volume_utilization: float
    weight_used_kg: float
    weight_limit_kg: Optional[float] = None
    weight_utilization: Optional[float] = None
    pack_length_mm: float = 0
    pack_width_mm: float = 0
    pack_height_mm: float = 0
    pack_surface_m2: float = 0
    container_volume_m3: Optional[float] = None
    # Placed cargo / full container inner volume. Primary FCL figure.
    container_volume_utilization: float = 0
    # Placed weight / container payload. Same ratio as weight_utilization.
    container_weight_utilization: Optional[float] = None
    remaining_volume_m3: float = 0
    remaining_weight_kg: Optional[float] = None
    cog_x_mm: float = 0
    cog_y_mm: float = 0
    cog_z_mm: float = 0
    cog_ok: bool = True
    door_axis: str = "x+"  # unload toward +length (container door)


class PackResponse(BaseModel):
    container: ContainerIn
    placements: List[PlacementOut]
    unplaced: List[str]
    stats: PackStats


class CompareRequest(BaseModel):
    items: List[ItemIn]
    cog_band: float = Field(0.15, ge=0.05, le=0.5)


class CompareOption(BaseModel):
    code: str
    length: float
    width: float
    height: float
    max_weight: float
    fits: bool
    container_volume_utilization: float
    container_weight_utilization: Optional[float] = None
    remaining_volume_m3: float
    remaining_weight_kg: Optional[float] = None
    bottleneck: Optional[str] = None
    bottleneck_label: Optional[str] = None
    detail: Optional[str] = None
    causes: List[str] = Field(default_factory=list)
    short_volume_m3: float = 0
    short_weight_kg: float = 0
    short_height_mm: float = 0
    placed_count: int
    unplaced_count: int


class CompareResponse(BaseModel):
    recommended: Optional[str] = None
    options: List[CompareOption]
