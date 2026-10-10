import type { ContainerIn, ItemIn, PlacementOut } from "./types";

/** Snap translation to a nearby wall or carton face, in millimetres. */
export const SNAP_MM = 40;

export function sourceItem(pieceId: string, items: ItemIn[]): ItemIn | undefined {
  const direct = items.find((item) => item.id === pieceId);
  if (direct) return direct;
  const match = /^(.*)#\d+$/.exec(pieceId);
  if (!match) return undefined;
  return items.find((item) => item.id === match[1]);
}

function snapAxis(
  value: number,
  boxSize: number,
  anchors: number[],
  limit: number,
  threshold: number
): number {
  const candidates = [0, Math.max(0, limit - boxSize)];
  for (const edge of anchors) {
    candidates.push(edge, edge - boxSize);
  }
  let best = value;
  let bestDist = threshold;
  for (const candidate of candidates) {
    const clamped = Math.max(0, Math.min(candidate, Math.max(0, limit - boxSize)));
    const distance = Math.abs(clamped - value);
    if (distance < bestDist - 1e-6 || (Math.abs(distance - bestDist) <= 1e-6 && clamped < best)) {
      bestDist = distance;
      best = clamped;
    }
  }
  return best;
}

export function snapXY(
  x: number,
  y: number,
  length: number,
  width: number,
  others: PlacementOut[],
  container: ContainerIn,
  threshold = SNAP_MM
): { x: number; y: number } {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const other of others) {
    xs.push(other.x, other.x + other.length);
    ys.push(other.y, other.y + other.width);
  }
  return {
    x: snapAxis(x, length, xs, container.length, threshold),
    y: snapAxis(y, width, ys, container.width, threshold),
  };
}

function overlapsXY(
  x: number,
  y: number,
  length: number,
  width: number,
  other: PlacementOut
): boolean {
  return (
    x < other.x + other.length - 1e-6 &&
    other.x < x + length - 1e-6 &&
    y < other.y + other.width - 1e-6 &&
    other.y < y + width - 1e-6
  );
}

/** Slide a carton out of floor overlaps so a 90° turn can stay supported. */
export function separateOnFloor(
  x: number,
  y: number,
  length: number,
  width: number,
  height: number,
  others: PlacementOut[],
  container: ContainerIn
): { x: number; y: number } | null {
  let px = Math.max(0, Math.min(x, container.length - length));
  let py = Math.max(0, Math.min(y, container.width - width));
  if (px < -1e-6 || py < -1e-6) return null;
  for (let guard = 0; guard < others.length + 2; guard++) {
    const blocker = others.find(
      (other) =>
        overlapsXY(px, py, length, width, other) &&
        other.z < height - 1e-6 &&
        other.z + other.height > 1e-6
    );
    if (!blocker) return { x: px, y: py };
    const options = [
      { x: blocker.x - length, y: py },
      { x: blocker.x + blocker.length, y: py },
      { x: px, y: blocker.y - width },
      { x: px, y: blocker.y + blocker.width },
    ].filter(
      (option) =>
        option.x >= -1e-6 &&
        option.y >= -1e-6 &&
        option.x + length <= container.length + 1e-6 &&
        option.y + width <= container.width + 1e-6
    );
    if (options.length === 0) return null;
    options.sort(
      (a, b) => Math.hypot(a.x - px, a.y - py) - Math.hypot(b.x - px, b.y - py)
    );
    px = options[0].x;
    py = options[0].y;
  }
  return null;
}

/** Rest the carton on the highest surface it intersects, or the floor. */
export function dropZ(
  x: number,
  y: number,
  length: number,
  width: number,
  height: number,
  others: PlacementOut[],
  containerHeight: number
): number | null {
  let z = 0;
  for (let guard = 0; guard < others.length + 3; guard++) {
    let raiseTo: number | null = null;
    for (const other of others) {
      const overlapsXY =
        x < other.x + other.length - 1e-6 &&
        other.x < x + length - 1e-6 &&
        y < other.y + other.width - 1e-6 &&
        other.y < y + width - 1e-6;
      if (!overlapsXY) continue;
      const top = other.z + other.height;
      if (z < top - 1e-6 && z + height > other.z + 1e-6) {
        raiseTo = raiseTo == null ? top : Math.max(raiseTo, top);
      }
    }
    if (raiseTo == null) {
      if (z + height > containerHeight + 1e-6) return null;
      return z;
    }
    z = raiseTo;
    if (z + height > containerHeight + 1e-6) return null;
  }
  return null;
}
