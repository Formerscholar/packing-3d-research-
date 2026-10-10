export interface ItemIn {
  id: string;
  name?: string;
  length: number;
  width: number;
  height: number;
  weight: number;
  qty: number;
  allow_rotate?: boolean;
}

export interface ContainerIn {
  name: string;
  length: number;
  width: number;
  height: number;
  max_weight?: number | null;
}

export interface PlacementOut {
  id: string;
  name?: string | null;
  x: number;
  y: number;
  z: number;
  length: number;
  width: number;
  height: number;
  weight: number;
  rotated: boolean;
}

export interface PackStats {
  placed_count: number;
  unplaced_count: number;
  volume_used_m3: number;
  volume_total_m3: number;
  volume_utilization: number;
  weight_used_kg: number;
  weight_limit_kg?: number | null;
  weight_utilization?: number | null;
}

export interface PackRequest {
  container: ContainerIn;
  items: ItemIn[];
}

export interface PackResponse {
  container: ContainerIn;
  placements: PlacementOut[];
  unplaced: string[];
  stats: PackStats;
}
