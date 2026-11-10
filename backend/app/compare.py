"""Pack one SKU list into 20GP, 40GP, and 40HQ and explain what fails."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .containers import CATALOG, STANDARD_ORDER, ContainerSpec
from .engine import pack
from .models import (
    CompareOption,
    CompareResponse,
    ContainerIn,
    ItemIn,
    PackResponse,
)

# When several constraints fail, the first one is the primary bottleneck.
# Height is a piece that cannot enter this cabinet. Weight is a payload
# limit. Volume is everything else that still does not fit (floor, stack
# space, or packing leftover).
_CAUSE_ORDER = ("height", "weight", "volume")
_LABELS = {"height": "高度", "weight": "重量", "volume": "体积"}


def _pieces(items: Sequence[ItemIn]) -> List[Tuple[str, ItemIn]]:
    rows: List[Tuple[str, ItemIn]] = []
    for item in items:
        for index in range(item.qty):
            piece_id = f"{item.id}#{index + 1}" if item.qty > 1 else item.id
            rows.append((piece_id, item))
    return rows


def _container(spec: ContainerSpec, cog_band: float) -> ContainerIn:
    return ContainerIn(
        name=spec.code,
        length=spec.length,
        width=spec.width,
        height=spec.height,
        max_weight=spec.max_weight,
        cog_band=cog_band,
    )


def _detail(
    primary: str,
    causes: Sequence[str],
    short_height: float,
    short_weight: float,
    short_volume: float,
) -> str:
    parts: List[str] = []
    if "height" in causes:
        parts.append(f"卡了高度，高出柜内高 {short_height:.0f} mm")
    if "weight" in causes:
        if short_weight > 1e-6:
            parts.append(f"卡了重量，超出限重 {short_weight:.0f} kg")
        else:
            parts.append("卡了重量，剩余载重不够放下未装货物")
    if "volume" in causes:
        parts.append(f"卡了体积，还有 {short_volume:.3f} m³ 没装下")
    if len(parts) == 1:
        return parts[0]
    return f"主要卡在{_LABELS[primary]}。" + "；".join(parts)


def _option(spec: ContainerSpec, items: Sequence[ItemIn], result: PackResponse) -> CompareOption:
    stats = result.stats
    pieces = _pieces(items)
    unplaced_ids = set(result.unplaced)
    total_weight = sum(item.weight * item.qty for item in items)
    max_weight = spec.max_weight
    placed_weight = stats.weight_used_kg
    fits = stats.unplaced_count == 0 and placed_weight <= max_weight + 1e-6

    causes: set[str] = set()
    short_height = 0.0
    short_volume_raw = 0.0
    remaining_payload = max_weight - placed_weight

    if not fits:
        if total_weight > max_weight + 1e-6:
            causes.add("weight")
        for piece_id, item in pieces:
            if piece_id not in unplaced_ids:
                continue
            if item.height > spec.height + 1e-6:
                causes.add("height")
                short_height = max(short_height, item.height - spec.height)
                continue
            if item.weight > remaining_payload + 1e-6:
                causes.add("weight")
                continue
            causes.add("volume")
            short_volume_raw += item.length * item.width * item.height
        if not causes:
            causes.add("volume")

    ordered = [name for name in _CAUSE_ORDER if name in causes]
    primary = ordered[0] if ordered else None
    short_weight = max(total_weight - max_weight, 0.0) if "weight" in causes else 0.0
    short_volume = short_volume_raw / 1e9 if "volume" in causes else 0.0
    detail: Optional[str] = None
    if primary is not None:
        detail = _detail(primary, ordered, short_height, short_weight, short_volume)

    return CompareOption(
        code=spec.code,
        length=spec.length,
        width=spec.width,
        height=spec.height,
        max_weight=spec.max_weight,
        fits=fits,
        container_volume_utilization=stats.container_volume_utilization,
        container_weight_utilization=stats.container_weight_utilization,
        remaining_volume_m3=stats.remaining_volume_m3,
        remaining_weight_kg=stats.remaining_weight_kg,
        bottleneck=primary,
        bottleneck_label=_LABELS[primary] if primary else None,
        detail=detail,
        causes=ordered,
        short_volume_m3=round(short_volume, 4),
        short_weight_kg=round(short_weight, 2),
        short_height_mm=round(short_height, 1),
        placed_count=stats.placed_count,
        unplaced_count=stats.unplaced_count,
    )


def compare_containers(items: Sequence[ItemIn], cog_band: float = 0.15) -> CompareResponse:
    """Recommend the smallest standard container that can take every piece."""
    options = [
        _option(CATALOG[code], items, pack(_container(CATALOG[code], cog_band), items))
        for code in STANDARD_ORDER
    ]
    recommended = next((row.code for row in options if row.fits), None)
    return CompareResponse(recommended=recommended, options=options)
