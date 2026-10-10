"""Pydantic request/response models for the packing API."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


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


class ContainerIn(BaseModel):
    """Container / cabinet inner dimensions (mm) and optional max weight (kg)."""

    name: str = "20GP"
    length: float = Field(5898, gt=0)
    width: float = Field(2352, gt=0)
    height: float = Field(2393, gt=0)
    max_weight: Optional[float] = Field(28200, description="kg, optional")


class PackRequest(BaseModel):
    container: ContainerIn = Field(default_factory=ContainerIn)
    items: List[ItemIn]


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


class PackStats(BaseModel):
    placed_count: int
    unplaced_count: int
    volume_used_m3: float
    volume_total_m3: float
    volume_utilization: float
    weight_used_kg: float
    weight_limit_kg: Optional[float] = None
    weight_utilization: Optional[float] = None


class PackResponse(BaseModel):
    container: ContainerIn
    placements: List[PlacementOut]
    unplaced: List[str]
    stats: PackStats
