"""Simple Extreme-Point / First-Fit Decreasing 3D packer.

Axis-aligned boxes only. Optional 90° yaw (swap L/W). Good enough for MVP demos;
not a production CLP solver (no stacking strength, COG, LIFO unload, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
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
    """Return (l, w, h, rotated). Height stays upright for MVP."""
    opts = [(box.l, box.w, box.h, False)]
    if box.allow_rotate and abs(box.l - box.w) > 1e-6:
        opts.append((box.w, box.l, box.h, True))
    return opts


def pack(container: ContainerIn, items: Sequence[ItemIn]) -> PackResponse:
    """FFD by volume, Extreme-Point candidate positions."""
    boxes: List[_Box] = []
    for it in items:
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
                )
            )

    boxes.sort(key=lambda b: b.l * b.w * b.h, reverse=True)

    cl, cw, ch = container.length, container.width, container.height
    placed: List[_Placed] = []
    unplaced: List[str] = []
    weight_used = 0.0
    max_w = container.max_weight
    eps: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0)]

    for box in boxes:
        if max_w is not None and weight_used + box.weight > max_w + 1e-6:
            unplaced.append(box.id)
            continue

        # (z, y, x, px, py, pz, l, w, h, rot) — prefer lower layer then front-left
        best_key: Optional[Tuple] = None
        best_pose: Optional[Tuple[float, float, float, float, float, float, bool]] = None

        for px, py, pz in eps:
            for l, w, h, rot in _orientations(box):
                if _fits(px, py, pz, l, w, h, cl, cw, ch, placed):
                    key = (pz, py, px)
                    if best_key is None or key < best_key:
                        best_key = key
                        best_pose = (px, py, pz, l, w, h, rot)

        if best_pose is None:
            unplaced.append(box.id)
            continue

        bx, by, bz, bl, bw, bh, brot = best_pose
        placed.append(
            _Placed(box=box, x=bx, y=by, z=bz, l=bl, w=bw, h=bh, rotated=brot)
        )
        weight_used += box.weight

        for ep in ((bx + bl, by, bz), (bx, by + bw, bz), (bx, by, bz + bh)):
            if ep[0] < cl - 1e-6 and ep[1] < cw - 1e-6 and ep[2] < ch - 1e-6:
                if ep not in eps:
                    eps.append(ep)

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
        eps = pruned if pruned else [(0.0, 0.0, 0.0)]

    vol_used = sum(p.l * p.w * p.h for p in placed) / 1e9
    vol_total = (cl * cw * ch) / 1e9
    util = (vol_used / vol_total) if vol_total > 0 else 0.0
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
        )
        for p in placed
    ]

    return PackResponse(
        container=container,
        placements=placements,
        unplaced=unplaced,
        stats=PackStats(
            placed_count=len(placements),
            unplaced_count=len(unplaced),
            volume_used_m3=round(vol_used, 4),
            volume_total_m3=round(vol_total, 4),
            volume_utilization=round(util, 4),
            weight_used_kg=round(weight_used, 2),
            weight_limit_kg=max_w,
            weight_utilization=round(w_util, 4) if w_util is not None else None,
        ),
    )
