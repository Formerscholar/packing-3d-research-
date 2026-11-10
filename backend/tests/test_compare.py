"""Full-container utilization and standard container comparison."""

from fastapi.testclient import TestClient

from app.engine import evaluate_layout, pack
from app.main import app
from app.models import ContainerIn, ItemIn, PlacementOut

client = TestClient(app)


def _item(item_id: str, **kwargs) -> ItemIn:
    data = dict(
        id=item_id,
        name=item_id,
        length=400,
        width=400,
        height=400,
        weight=10,
        qty=1,
        allow_rotate=False,
        stackable=True,
    )
    data.update(kwargs)
    return ItemIn(**data)


def test_pack_stats_keep_tightness_and_add_full_container_remaining():
    """Tightness stays relative to the compact box; FCL numbers use the whole container."""
    container = ContainerIn(name="t", length=1000, width=1000, height=1000, max_weight=100)
    result = pack(container, [_item("A", length=500, width=400, height=200, weight=25)])
    stats = result.stats

    assert stats.unplaced_count == 0
    assert stats.volume_utilization == 1
    assert stats.volume_used_m3 == 0.04
    assert stats.volume_total_m3 == 0.04
    assert stats.container_volume_m3 == 1
    assert stats.container_volume_utilization == 0.04
    assert stats.remaining_volume_m3 == 0.96
    assert stats.weight_utilization == 0.25
    assert stats.container_weight_utilization == 0.25
    assert stats.remaining_weight_kg == 75


def test_layout_recompute_includes_full_container_remaining():
    container = ContainerIn(name="t", length=1000, width=1000, height=1000, max_weight=100)
    items = [_item("A", length=500, width=400, height=200, weight=25)]
    placed = [
        PlacementOut(
            id="A",
            x=0,
            y=0,
            z=0,
            length=500,
            width=400,
            height=200,
            weight=25,
            rotated=False,
        )
    ]
    stats = evaluate_layout(container, items, placed).stats
    assert stats.volume_utilization == 1
    assert stats.container_volume_utilization == 0.04
    assert stats.remaining_volume_m3 == 0.96
    assert stats.remaining_weight_kg == 75


def _floor_box(qty: int, weight: float = 10) -> dict:
    """One layer fills a 20GP floor; a second layer is taller than 40HQ."""
    return {
        "id": "FLOOR",
        "name": "地板货",
        "length": 5898,
        "width": 2352,
        "height": 2000,
        "weight": weight,
        "qty": qty,
        "allow_rotate": False,
        "stackable": True,
    }


def test_compare_recommends_smallest_container_that_fits():
    """Two floor-sized cartons need 40' length, and 40GP is smaller than 40HQ."""
    res = client.post("/api/pack/compare", json={"items": [_floor_box(2)]})
    assert res.status_code == 200
    body = res.json()
    by_code = {row["code"]: row for row in body["options"]}

    assert [row["code"] for row in body["options"]] == ["20GP", "40GP", "40HQ"]
    assert by_code["20GP"]["length"] == 5898
    assert by_code["20GP"]["width"] == 2352
    assert by_code["20GP"]["height"] == 2393
    assert by_code["20GP"]["max_weight"] == 28200
    assert by_code["40GP"]["length"] == 12032
    assert by_code["40GP"]["width"] == 2352
    assert by_code["40GP"]["height"] == 2393
    assert by_code["40GP"]["max_weight"] == 26680
    assert by_code["40HQ"]["length"] == 12032
    assert by_code["40HQ"]["width"] == 2352
    assert by_code["40HQ"]["height"] == 2698
    assert by_code["40HQ"]["max_weight"] == 26580

    assert by_code["20GP"]["fits"] is False
    assert by_code["40GP"]["fits"] is True
    assert by_code["40HQ"]["fits"] is True
    assert body["recommended"] == "40GP"
    assert by_code["20GP"]["bottleneck"] == "volume"
    assert by_code["20GP"]["bottleneck_label"] == "体积"
    assert by_code["20GP"]["short_volume_m3"] == round(5898 * 2352 * 2000 / 1e9, 4)
    assert by_code["40GP"]["bottleneck"] is None
    assert by_code["40GP"]["remaining_volume_m3"] >= 0
    assert by_code["40GP"]["container_volume_utilization"] > 0
    assert by_code["40GP"]["container_weight_utilization"] is not None
    assert by_code["40GP"]["remaining_weight_kg"] is not None


def test_compare_recommends_20gp_when_every_standard_type_fits():
    res = client.post(
        "/api/pack/compare",
        json={"items": [_item("A", length=400, width=300, height=300, weight=8).model_dump()]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["recommended"] == "20GP"
    assert all(row["fits"] is True and row["bottleneck"] is None for row in body["options"])


def test_compare_height_bottleneck_recommends_40hq_only():
    res = client.post(
        "/api/pack/compare",
        json={
            "items": [
                {
                    "id": "TALL",
                    "name": "超高件",
                    "length": 1000,
                    "width": 1000,
                    "height": 2500,
                    "weight": 50,
                    "qty": 1,
                    "allow_rotate": False,
                }
            ]
        },
    )
    assert res.status_code == 200
    body = res.json()
    by_code = {row["code"]: row for row in body["options"]}
    assert by_code["20GP"]["fits"] is False
    assert by_code["40GP"]["fits"] is False
    assert by_code["40HQ"]["fits"] is True
    assert by_code["20GP"]["bottleneck"] == "height"
    assert by_code["40GP"]["bottleneck"] == "height"
    assert by_code["20GP"]["bottleneck_label"] == "高度"
    assert by_code["20GP"]["short_height_mm"] == 2500 - 2393
    assert "高度" in by_code["20GP"]["detail"]
    assert body["recommended"] == "40HQ"


def test_compare_weight_bottleneck_recommends_none():
    res = client.post(
        "/api/pack/compare",
        json={
            "items": [
                {
                    "id": "HEAVY",
                    "name": "超重件",
                    "length": 500,
                    "width": 500,
                    "height": 500,
                    "weight": 30000,
                    "qty": 1,
                    "allow_rotate": False,
                }
            ]
        },
    )
    assert res.status_code == 200
    body = res.json()
    by_code = {row["code"]: row for row in body["options"]}
    assert body["recommended"] is None
    assert all(row["fits"] is False for row in body["options"])
    assert by_code["20GP"]["bottleneck"] == "weight"
    assert by_code["40GP"]["bottleneck"] == "weight"
    assert by_code["40HQ"]["bottleneck"] == "weight"
    assert by_code["20GP"]["bottleneck_label"] == "重量"
    assert by_code["20GP"]["short_weight_kg"] == 30000 - 28200
    assert by_code["40GP"]["short_weight_kg"] == 30000 - 26680
    assert by_code["40HQ"]["short_weight_kg"] == 30000 - 26580
    assert "重量" in by_code["20GP"]["detail"]


def test_compare_keeps_20gp_when_only_its_payload_is_enough():
    """40GP/40HQ payloads are lower than this 20GP series, so heavier cargo stays on 20GP."""
    res = client.post(
        "/api/pack/compare",
        json={
            "items": [
                {
                    "id": "DENSE",
                    "name": "高密度",
                    "length": 400,
                    "width": 400,
                    "height": 400,
                    "weight": 28200,
                    "qty": 1,
                    "allow_rotate": False,
                }
            ]
        },
    )
    assert res.status_code == 200
    body = res.json()
    by_code = {row["code"]: row for row in body["options"]}
    assert body["recommended"] == "20GP"
    assert by_code["20GP"]["fits"] is True
    assert by_code["40GP"]["fits"] is False
    assert by_code["40HQ"]["fits"] is False
    assert by_code["40GP"]["bottleneck"] == "weight"


def test_compare_names_height_and_weight_when_both_block():
    res = client.post(
        "/api/pack/compare",
        json={
            "items": [
                {
                    "id": "BOTH",
                    "name": "又高又重",
                    "length": 800,
                    "width": 800,
                    "height": 2500,
                    "weight": 30000,
                    "qty": 1,
                    "allow_rotate": False,
                }
            ]
        },
    )
    assert res.status_code == 200
    body = res.json()
    by_code = {row["code"]: row for row in body["options"]}
    assert body["recommended"] is None
    assert by_code["20GP"]["bottleneck"] == "height"
    assert set(by_code["20GP"]["causes"]) == {"height", "weight"}
    assert "高度" in by_code["20GP"]["detail"]
    assert "重量" in by_code["20GP"]["detail"]
    assert by_code["40HQ"]["bottleneck"] == "weight"
    assert by_code["40HQ"]["causes"] == ["weight"]


def test_compare_volume_shortfall_when_no_standard_container_fits():
    res = client.post("/api/pack/compare", json={"items": [_floor_box(3)]})
    assert res.status_code == 200
    body = res.json()
    by_code = {row["code"]: row for row in body["options"]}
    one = round(5898 * 2352 * 2000 / 1e9, 4)
    assert body["recommended"] is None
    assert by_code["20GP"]["bottleneck"] == "volume"
    assert by_code["40GP"]["bottleneck"] == "volume"
    assert by_code["40HQ"]["bottleneck"] == "volume"
    assert by_code["20GP"]["short_volume_m3"] == round(one * 2, 4)
    assert by_code["40GP"]["short_volume_m3"] == one
    assert by_code["40HQ"]["short_volume_m3"] == one


def test_export_summary_includes_full_container_metrics():
    body = {
        "container": {
            "name": "t",
            "length": 1000,
            "width": 1000,
            "height": 1000,
            "max_weight": 100,
        },
        "items": [
            {
                "id": "A",
                "name": "纸箱A",
                "length": 500,
                "width": 400,
                "height": 200,
                "weight": 25,
                "qty": 1,
                "allow_rotate": False,
            }
        ],
    }
    packed = client.post("/api/pack", json=body)
    assert packed.status_code == 200
    stats = packed.json()["stats"]
    assert stats["container_volume_utilization"] == 0.04
    assert stats["remaining_volume_m3"] == 0.96

    res = client.post("/api/pack/export?format=xlsx", json=body)
    assert res.status_code == 200
    from io import BytesIO

    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(res.content))
    summary = {row[0].value: row[1].value for row in wb["装箱汇总"].iter_rows() if row[0].value}
    assert summary["装箱紧密度%"] == round(stats["volume_utilization"] * 100, 2)
    assert summary["整柜体积利用率%"] == round(stats["container_volume_utilization"] * 100, 2)
    assert summary["剩余体积(m³)"] == stats["remaining_volume_m3"]
    assert summary["剩余重量(kg)"] == stats["remaining_weight_kg"]
