"""Compact 3D packer with load-bearing, COG, and LIFO order.

Minimizes outer carton surface (then volume). Optional container dims are a
hard upper bound. Stacking checks support area and crush capacity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .models import (
    ContainerIn,
    ItemIn,
    PackResponse,
    PackStats,
    PlacementOut,
)


@dataclass
class _Box:
    id: str
    name: Optional[str]
    l: float
    w: float
    h: float
    weight: float
    allow_rotate: bool
    max_stack_load_kg: float
    stackable: bool


@dataclass
class _Placed:
    box: _Box
    x: float
    y: float
    z: float
    l: float
    w: float
    h: float
    rotated: bool
    load_on_top: float = 0.0  # kg currently resting on this carton


def _aabb_overlap(
    a: Tuple[float, float, float, float, float, float],
    b: Tuple[float, float, float, float, float, float],
) -> bool:
    ax, ay, az, al, aw, ah = a
    bx, by, bz, bl, bw, bh = b
    return not (
        ax + al <= bx
        or bx + bl <= ax
        or ay + aw <= by
        or by + bw <= ay
        or az + ah <= bz
        or bz + bh <= az
    )


def _fits(
    x: float,
    y: float,
    z: float,
    l: float,
    w: float,
    h: float,
    cl: float,
    cw: float,
    ch: float,
    placed: Sequence[_Placed],
) -> bool:
    if x < 0 or y < 0 or z < 0:
        return False
    if x + l > cl + 1e-6 or y + w > cw + 1e-6 or z + h > ch + 1e-6:
        return False
    cand = (x, y, z, l, w, h)
    for p in placed:
        if _aabb_overlap(cand, (p.x, p.y, p.z, p.l, p.w, p.h)):
            return False
    return True


def _orientations(box: _Box) -> List[Tuple[float, float, float, bool]]:
    opts = [(box.l, box.w, box.h, False)]
    if box.allow_rotate and abs(box.l - box.w) > 1e-6:
        opts.append((box.w, box.l, box.h, True))
    return opts


def _supporters(
    x: float, y: float, z: float, l: float, w: float, placed: Sequence[_Placed]
) -> List[Tuple[_Placed, float]]:
    """Return (support_box, overlap_area) for boxes whose top touches z."""
    out: List[Tuple[_Placed, float]] = []
    if z <= 1e-6:
        return out
    for p in placed:
        if abs((p.z + p.h) - z) > 1e-3:
            continue
        ox0 = max(x, p.x)
        oy0 = max(y, p.y)
        ox1 = min(x + l, p.x + p.l)
        oy1 = min(y + w, p.y + p.w)
        if ox1 > ox0 and oy1 > oy0:
            out.append((p, (ox1 - ox0) * (oy1 - oy0)))
    return out


def _support_ok(
    x: float,
    y: float,
    z: float,
    l: float,
    w: float,
    placed: Sequence[_Placed],
    min_ratio: float = 0.85,
) -> bool:
    if z <= 1e-6:
        return True
    area = l * w
    if area <= 0:
        return False
    supporters = _supporters(x, y, z, l, w, placed)
    supported = sum(a for _, a in supporters)
    if supported / area < min_ratio - 1e-9:
        return False
    # All supporters must allow stacking
    return all(p.box.stackable for p, _ in supporters)


def _load_bearing_ok(
    x: float,
    y: float,
    z: float,
    l: float,
    w: float,
    weight: float,
    placed: Sequence[_Placed],
) -> bool:
    """Distribute new weight across supporters by overlap area; check capacity."""
    if z <= 1e-6:
        return True
    supporters = _supporters(x, y, z, l, w, placed)
    if not supporters:
        return False
    total_area = sum(a for _, a in supporters)
    if total_area <= 0:
        return False
    for p, area in supporters:
        share = weight * (area / total_area)
        if p.load_on_top + share > p.box.max_stack_load_kg + 1e-6:
            return False
    return True


def _apply_load(
    x: float,
    y: float,
    z: float,
    l: float,
    w: float,
    weight: float,
    placed: Sequence[_Placed],
) -> None:
    if z <= 1e-6:
        return
    supporters = _supporters(x, y, z, l, w, placed)
    total_area = sum(a for _, a in supporters)
    if total_area <= 0:
        return
    for p, area in supporters:
        p.load_on_top += weight * (area / total_area)


def _surface(L: float, W: float, H: float) -> float:
    return 2.0 * (L * W + L * H + W * H)


def _bbox_of(placed: Sequence[_Placed]) -> Tuple[float, float, float]:
    if not placed:
        return 0.0, 0.0, 0.0
    return (
        max(p.x + p.l for p in placed),
        max(p.y + p.w for p in placed),
        max(p.z + p.h for p in placed),
    )


def _add_eps(
    eps: List[Tuple[float, float, float]],
    points: Sequence[Tuple[float, float, float]],
    cl: float,
    cw: float,
    ch: float,
) -> None:
    for ep in points:
        if ep[0] < cl - 1e-6 and ep[1] < cw - 1e-6 and ep[2] < ch - 1e-6:
            if ep not in eps:
                eps.append(ep)


def _prune_eps(
    eps: List[Tuple[float, float, float]], placed: Sequence[_Placed]
) -> List[Tuple[float, float, float]]:
    pruned: List[Tuple[float, float, float]] = []
    for ep in eps:
        inside = False
        for p in placed:
            if (
                p.x <= ep[0] < p.x + p.l - 1e-9
                and p.y <= ep[1] < p.y + p.w - 1e-9
                and p.z <= ep[2] < p.z + p.h - 1e-9
            ):
                inside = True
                break
        if not inside:
            pruned.append(ep)
    return pruned if pruned else [(0.0, 0.0, 0.0)]


def _default_crush(weight: float, explicit: Optional[float]) -> float:
    if explicit is not None:
        return explicit
    # Conservative default: can carry 5x own weight on top
    return max(weight * 5.0, 1.0)


def pack(container: ContainerIn, items: Sequence[ItemIn]) -> PackResponse:
    boxes: List[_Box] = []
    for it in items:
        crush = _default_crush(it.weight, it.max_stack_load_kg)
        for i in range(it.qty):
            boxes.append(
                _Box(
                    id=f"{it.id}#{i + 1}" if it.qty > 1 else it.id,
                    name=it.name or it.id,
                    l=it.length,
                    w=it.width,
                    h=it.height,
                    weight=it.weight,
                    allow_rotate=it.allow_rotate,
                    max_stack_load_kg=crush,
                    stackable=it.stackable,
                )
            )

    # Heavier / larger first; fragile (low crush) slightly later among equals
    boxes.sort(
        key=lambda b: (b.l * b.w * b.h, b.weight, b.max_stack_load_kg),
        reverse=True,
    )

    cl, cw, ch = container.length, container.width, container.height
    placed: List[_Placed] = []
    unplaced: List[str] = []
    weight_used = 0.0
    max_w = container.max_weight
    eps: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
    bx_l = bx_w = bx_h = 0.0

    for box in boxes:
        if max_w is not None and weight_used + box.weight > max_w + 1e-6:
            unplaced.append(box.id)
            continue

        best_key: Optional[Tuple] = None
        best_pose: Optional[Tuple[float, float, float, float, float, float, bool]] = None

        for px, py, pz in eps:
            for l, w, h, rot in _orientations(box):
                if not _fits(px, py, pz, l, w, h, cl, cw, ch, placed):
                    continue
                if not _support_ok(px, py, pz, l, w, placed):
                    continue
                if not _load_bearing_ok(px, py, pz, l, w, box.weight, placed):
                    continue
                nl = max(bx_l, px + l)
                nw = max(bx_w, py + w)
                nh = max(bx_h, pz + h)
                surf = _surface(nl, nw, nh)
                vol = nl * nw * nh
                # Prefer compact pack; slight preference for lower z (stable)
                key = (surf, vol, nh, nw, nl, pz, py, px)
                if best_key is None or key < best_key:
                    best_key = key
                    best_pose = (px, py, pz, l, w, h, rot)

        if best_pose is None:
            unplaced.append(box.id)
            continue

        x, y, z, l, w, h, rot = best_pose
        _apply_load(x, y, z, l, w, box.weight, placed)
        placed.append(
            _Placed(box=box, x=x, y=y, z=z, l=l, w=w, h=h, rotated=rot)
        )
        weight_used += box.weight
        bx_l = max(bx_l, x + l)
        bx_w = max(bx_w, y + w)
        bx_h = max(bx_h, z + h)

        _add_eps(
            eps,
            (
                (x + l, y, z),
                (x, y + w, z),
                (x, y, z + h),
                (x + l, y, z + h),
                (x, y + w, z + h),
                (x + l, y + w, z),
                (x + l, y + w, z + h),
            ),
            cl,
            cw,
            ch,
        )
        eps[:] = _prune_eps(eps, placed)

    # --- COG ---
    if placed and weight_used > 0:
        cog_x = sum((p.x + p.l / 2) * p.box.weight for p in placed) / weight_used
        cog_y = sum((p.y + p.w / 2) * p.box.weight for p in placed) / weight_used
        cog_z = sum((p.z + p.h / 2) * p.box.weight for p in placed) / weight_used
    else:
        cog_x = cog_y = cog_z = 0.0

    pack_l, pack_w, pack_h = _bbox_of(placed)
    # Soft band vs packed outer box center (material-oriented pack)
    cx, cy = pack_l / 2, pack_w / 2
    band = container.cog_band
    cog_ok = (
        abs(cog_x - cx) <= pack_l * band + 1e-6
        and abs(cog_y - cy) <= pack_w * band + 1e-6
    ) if pack_l > 0 and pack_w > 0 else True

    # --- LIFO: door at +X (container rear). First unload = largest x (near door). ---
    indexed = list(enumerate(placed))
    indexed.sort(key=lambda ip: (-(ip[1].x + ip[1].l / 2), -(ip[1].z), ip[1].y))
    unload_rank = {i: rank + 1 for rank, (i, _) in enumerate(indexed)}
    # load_order inverse of unload (back first)
    load_indexed = sorted(
        enumerate(placed),
        key=lambda ip: (ip[1].x + ip[1].l / 2, ip[1].z, ip[1].y),
    )
    load_rank = {i: rank + 1 for rank, (i, _) in enumerate(load_indexed)}

    vol_used = sum(p.l * p.w * p.h for p in placed) / 1e9
    pack_vol = (pack_l * pack_w * pack_h) / 1e9 if placed else 0.0
    util = (vol_used / pack_vol) if pack_vol > 0 else 0.0
    cont_vol = (cl * cw * ch) / 1e9
    surf_m2 = _surface(pack_l, pack_w, pack_h) / 1e6 if placed else 0.0
    w_util = (weight_used / max_w) if max_w and max_w > 0 else None

    placements = [
        PlacementOut(
            id=p.box.id,
            name=p.box.name,
            x=p.x,
            y=p.y,
            z=p.z,
            length=p.l,
            width=p.w,
            height=p.h,
            weight=p.box.weight,
            rotated=p.rotated,
            unload_order=unload_rank[i],
            load_order=load_rank[i],
        )
        for i, p in enumerate(placed)
    ]

    return PackResponse(
        container=container,
        placements=placements,
        unplaced=unplaced,
        stats=PackStats(
            placed_count=len(placements),
            unplaced_count=len(unplaced),
            volume_used_m3=round(vol_used, 4),
            volume_total_m3=round(pack_vol, 4),
            volume_utilization=round(util, 4),
            weight_used_kg=round(weight_used, 2),
            weight_limit_kg=max_w,
            weight_utilization=round(w_util, 4) if w_util is not None else None,
            pack_length_mm=round(pack_l, 1),
            pack_width_mm=round(pack_w, 1),
            pack_height_mm=round(pack_h, 1),
            pack_surface_m2=round(surf_m2, 4),
            container_volume_m3=round(cont_vol, 4),
            cog_x_mm=round(cog_x, 1),
            cog_y_mm=round(cog_y, 1),
            cog_z_mm=round(cog_z, 1),
            cog_ok=cog_ok,
            door_axis="x+",
        ),
    )
