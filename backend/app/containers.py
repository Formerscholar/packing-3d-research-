"""Standard dry-container catalog for the sample preset and compare API.

Dimensions are internal millimeters. Payload is kilograms.

20GP is the existing sample and stays fixed: 5898 × 2352 × 2393 mm, 28200 kg.
40GP and 40HQ keep that same internal width.

40' internal length is 12032 mm, not 2 × 5898. A 40' box has the same end
frames plus another pair of corner posts, so the clear length is a little
more than twice a 20'. GP height stays 2393 mm. 40HQ uses the usual high-cube
internal height, 2698 mm (GP height + 305 mm).

Payloads are the common max-cargo figures published with this internal-size
series. 20GP stays at 28200 kg. 40GP (26680 kg) and 40HQ (26580 kg) are
slightly lower because a 40' tare is higher at a similar gross rating.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContainerSpec:
    code: str
    length: float
    width: float
    height: float
    max_weight: float
    cog_band: float = 0.15


# Smallest to largest. Recommendation walks this order.
STANDARD_ORDER: tuple[str, ...] = ("20GP", "40GP", "40HQ")

CATALOG: dict[str, ContainerSpec] = {
    "20GP": ContainerSpec("20GP", 5898, 2352, 2393, 28200),
    "40GP": ContainerSpec("40GP", 12032, 2352, 2393, 26680),
    "40HQ": ContainerSpec("40HQ", 12032, 2352, 2698, 26580),
}
