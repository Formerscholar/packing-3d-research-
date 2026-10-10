"""Load chain, LIFO search constraint, and manual layout recompute."""

from fastapi.testclient import TestClient

from app.engine import LayoutError, evaluate_layout, pack
from app.main import app
from app.models import ContainerIn, ItemIn, PlacementOut

client = TestClient(app)


def _box(item_id: str, seq: int | None = None, **kwargs) -> ItemIn:
    data = dict(
        id=item_id,
        name=item_id,
        length=100,
        width=100,
        height=100,
        weight=10,
        qty=1,
        allow_rotate=False,
        max_stack_load_kg=100,
        stackable=True,
    )
    data.update(kwargs)
    if seq is not None:
        data["unload_seq"] = seq
    return ItemIn(**data)


def test_crush_load_propagates_through_the_stack():
    """Middle can hold the top; the floor carton cannot hold top + middle."""
    container = ContainerIn(name="t", length=100, width=100, height=400, max_weight=1000)
    items = [
        _box("C", length=100, width=100, height=120, weight=5, max_stack_load_kg=20),
        _box("B", length=100, width=100, height=90, weight=10, max_stack_load_kg=100),
        _box("A", length=100, width=100, height=80, weight=12, max_stack_load_kg=100),
    ]
    result = pack(container, items)
    assert "A" in result.unplaced
    assert {p.id for p in result.placements} == {"B", "C"}


def test_pack_keeps_earlier_unload_in_front_of_later_unload():
    container = ContainerIn(name="t", length=300, width=100, height=100, max_weight=1000, cog_band=0.5)
    items = [
        _box("EARLY", unload_seq=1, length=200, width=100, height=100, weight=10),
        _box("LATE", unload_seq=2, length=100, width=100, height=100, weight=10),
    ]
    result = pack(container, items)
    assert result.stats.unplaced_count == 0
    early = next(p for p in result.placements if p.id == "EARLY")
    late = next(p for p in result.placements if p.id == "LATE")
    assert early.x + 1e-6 >= late.x + late.length


def test_layout_rejects_blocked_unload_and_recomputes_cog():
    container = ContainerIn(name="t", length=400, width=200, height=200, max_weight=1000, cog_band=0.5)
    items = [
        _box("LIGHT", unload_seq=1, weight=10),
        _box("HEAVY", unload_seq=2, weight=30),
    ]
    blocked = [
        PlacementOut(id="LIGHT", x=0, y=0, z=0, length=100, width=100, height=100, weight=10),
        PlacementOut(id="HEAVY", x=100, y=0, z=0, length=100, width=100, height=100, weight=30),
    ]
    try:
        evaluate_layout(container, items, blocked)
        raise AssertionError("blocked LIFO layout should fail")
    except LayoutError as exc:
        assert "装卸" in str(exc)

    placed = [
        PlacementOut(id="HEAVY", x=0, y=0, z=0, length=100, width=100, height=100, weight=30),
        PlacementOut(id="LIGHT", x=100, y=0, z=0, length=100, width=100, height=100, weight=10),
    ]
    result = evaluate_layout(container, items, placed)
    # centers 50 and 150 → (50*30 + 150*10) / 40 = 75
    assert result.stats.cog_x_mm == 75
    assert result.stats.volume_utilization == 1
    assert result.stats.placed_count == 2
    light = next(p for p in result.placements if p.id == "LIGHT")
    heavy = next(p for p in result.placements if p.id == "HEAVY")
    assert light.unload_order < heavy.unload_order


def test_layout_endpoint_rejects_overload_along_the_chain():
    body = {
        "container": {
            "name": "t",
            "length": 100,
            "width": 100,
            "height": 400,
            "max_weight": 1000,
        },
        "items": [
            {
                "id": "C",
                "length": 100,
                "width": 100,
                "height": 100,
                "weight": 5,
                "qty": 1,
                "allow_rotate": False,
                "max_stack_load_kg": 20,
            },
            {
                "id": "B",
                "length": 100,
                "width": 100,
                "height": 100,
                "weight": 10,
                "qty": 1,
                "allow_rotate": False,
                "max_stack_load_kg": 100,
            },
            {
                "id": "A",
                "length": 100,
                "width": 100,
                "height": 100,
                "weight": 12,
                "qty": 1,
                "allow_rotate": False,
                "max_stack_load_kg": 100,
            },
        ],
        "placements": [
            {"id": "C", "x": 0, "y": 0, "z": 0, "length": 100, "width": 100, "height": 100, "weight": 5},
            {"id": "B", "x": 0, "y": 0, "z": 100, "length": 100, "width": 100, "height": 100, "weight": 10},
            {"id": "A", "x": 0, "y": 0, "z": 200, "length": 100, "width": 100, "height": 100, "weight": 12},
        ],
    }
    res = client.post("/api/pack/layout", json=body)
    assert res.status_code == 400
    assert "承重" in res.json()["detail"]
