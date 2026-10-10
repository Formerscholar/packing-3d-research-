"""Compact 3D packer with load-bearing, COG, and LIFO order.

Minimizes outer carton surface (then volume). Optional container dims are a
hard upper bound. Stacking checks support area and crush capacity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

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
    unload_seq: Optional[int] = None


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


class LayoutError(ValueError):
    """Manual layout failed a physical or LIFO check."""


def _y_overlap(y: float, w: float, oy: float, ow: float) -> bool:
    return y + w > oy + 1e-6 and oy + ow > y + 1e-6


def _lifo_pose_ok(
    x: float,
    y: float,
    l: float,
    w: float,
    seq: Optional[int],
    placed: Sequence[_Placed],
) -> bool:
    """Earlier unload (smaller seq) must sit entirely toward the door (+X) in the same lane."""
    if seq is None:
        return True
    for p in placed:
        other = p.box.unload_seq
        if other is None or other == seq:
            continue
        if not _y_overlap(y, w, p.y, p.w):
            continue
        if seq < other:
            if x < p.x + p.l - 1e-6:
                return False
        elif x + l > p.x + 1e-6:
            return False
    return True


def _push_load(
    x: float,
    y: float,
    z: float,
    l: float,
    w: float,
    weight: float,
    placed: Sequence[_Placed],
    mutate: bool,
) -> Optional[str]:
    """Push weight onto direct supporters and down the stack. None means the chain holds."""
    if weight <= 0 or z <= 1e-6:
        return None
    supporters = _supporters(x, y, z, l, w, placed)
    if not supporters:
        return "悬空或支撑不足"
    total_area = sum(area for _, area in supporters)
    if total_area <= 0:
        return "悬空或支撑不足"
    pending: List[Tuple[_Placed, float]] = [
        (box, weight * (area / total_area)) for box, area in supporters
    ]
    extras: Dict[int, float] = {}
    steps = 0
    while pending:
        steps += 1
        if steps > 10000:
            return "承重计算超过层数上限"
        box, share = pending.pop()
        key = id(box)
        extras[key] = extras.get(key, 0.0) + share
        if not box.box.stackable:
            return "下方箱子不可承重"
        if box.load_on_top + extras[key] > box.box.max_stack_load_kg + 1e-6:
            return "承重超限"
        subs = _supporters(box.x, box.y, box.z, box.l, box.w, placed)
        if not subs:
            continue
        sub_area = sum(area for _, area in subs)
        if sub_area <= 0:
            continue
        for lower, area in subs:
            pending.append((lower, share * (area / sub_area)))
    if mutate:
        for box in placed:
            extra = extras.get(id(box))
            if extra:
                box.load_on_top += extra
    return None


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
                    unload_seq=it.unload_seq,
                )
            )

    # Later-unload (deeper) first, then larger / heavier cartons.
    boxes.sort(
        key=lambda b: (
            b.unload_seq is not None,
            b.unload_seq or 0,
            b.l * b.w * b.h,
            b.weight,
            b.max_stack_load_kg,
        ),
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
                if _push_load(px, py, pz, l, w, box.weight, placed, mutate=False):
                    continue
                if not _lifo_pose_ok(px, py, l, w, box.unload_seq, placed):
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
        _push_load(x, y, z, l, w, box.weight, placed, mutate=True)
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

    return _finalize(container, placed, unplaced, weight_used)


def _finalize(
    container: ContainerIn,
    placed: Sequence[_Placed],
    unplaced: Sequence[str],
    weight_used: float,
) -> PackResponse:
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
    cont_vol = (container.length * container.width * container.height) / 1e9
    surf_m2 = _surface(pack_l, pack_w, pack_h) / 1e6 if placed else 0.0
    max_w = container.max_weight
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


def _item_for_piece(piece_id: str, items: Sequence[ItemIn]) -> Optional[ItemIn]:
    by_id = {item.id: item for item in items}
    if piece_id in by_id:
        return by_id[piece_id]
    base, sep, suffix = piece_id.rpartition("#")
    if sep and suffix.isdigit() and base in by_id:
        return by_id[base]
    return None


def _piece_ids(items: Sequence[ItemIn]) -> List[str]:
    ids: List[str] = []
    for item in items:
        for index in range(item.qty):
            ids.append(f"{item.id}#{index + 1}" if item.qty > 1 else item.id)
    return ids


def evaluate_layout(
    container: ContainerIn,
    items: Sequence[ItemIn],
    poses: Sequence[PlacementOut],
) -> PackResponse:
    """Validate a hand-placed layout and recompute load, COG, utilization, and order."""
    if len({pose.id for pose in poses}) != len(list(poses)):
        raise LayoutError("箱子 id 重复")

    placed: List[_Placed] = []
    for pose in poses:
        src = _item_for_piece(pose.id, items)
        if (
            pose.x < -1e-6
            or pose.y < -1e-6
            or pose.z < -1e-6
            or pose.x + pose.length > container.length + 1e-6
            or pose.y + pose.width > container.width + 1e-6
            or pose.z + pose.height > container.height + 1e-6
        ):
            raise LayoutError("超出柜体")
        placed.append(
            _Placed(
                box=_Box(
                    id=pose.id,
                    name=pose.name or (src.name if src and src.name else pose.id),
                    l=pose.length,
                    w=pose.width,
                    h=pose.height,
                    weight=pose.weight,
                    allow_rotate=src.allow_rotate if src else True,
                    max_stack_load_kg=_default_crush(
                        pose.weight, src.max_stack_load_kg if src else None
                    ),
                    stackable=src.stackable if src else True,
                    unload_seq=src.unload_seq if src else None,
                ),
                x=pose.x,
                y=pose.y,
                z=pose.z,
                l=pose.length,
                w=pose.width,
                h=pose.height,
                rotated=pose.rotated,
            )
        )

    for index, box in enumerate(placed):
        for other in placed[index + 1 :]:
            if _aabb_overlap(
                (box.x, box.y, box.z, box.l, box.w, box.h),
                (other.x, other.y, other.z, other.l, other.w, other.h),
            ):
                raise LayoutError("与其他箱子重叠")

    weight_used = sum(box.box.weight for box in placed)
    if container.max_weight is not None and weight_used > container.max_weight + 1e-6:
        raise LayoutError("超过限重")

    for box in sorted(placed, key=lambda item: (item.z, item.y, item.x)):
        if not _support_ok(box.x, box.y, box.z, box.l, box.w, placed):
            raise LayoutError("悬空或支撑不足")
        issue = _push_load(
            box.x, box.y, box.z, box.l, box.w, box.box.weight, placed, mutate=False
        )
        if issue:
            raise LayoutError(issue)
        _push_load(box.x, box.y, box.z, box.l, box.w, box.box.weight, placed, mutate=True)

    for box in placed:
        others = [other for other in placed if other is not box]
        if not _lifo_pose_ok(box.x, box.y, box.l, box.w, box.box.unload_seq, others):
            raise LayoutError("装卸顺序冲突：先卸的货被挡在远离柜门的一侧")

    expected = _piece_ids(items)
    placed_ids = {box.box.id for box in placed}
    unplaced = [piece_id for piece_id in expected if piece_id not in placed_ids]
    return _finalize(container, placed, unplaced, weight_used)
