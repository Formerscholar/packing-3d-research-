export interface ItemIn {
  id: string;
  name?: string;
  length: number;
  width: number;
  height: number;
  weight: number;
  qty: number;
  allow_rotate?: boolean;
  max_stack_load_kg?: number | null;
  stackable?: boolean;
  unload_seq?: number | null;
}

export interface ContainerIn {
  name: string;
  length: number;
  width: number;
  height: number;
  max_weight?: number | null;
  cog_band?: number;
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
  unload_order?: number;
  load_order?: number;
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
  pack_length_mm?: number;
  pack_width_mm?: number;
  pack_height_mm?: number;
  pack_surface_m2?: number;
  container_volume_m3?: number | null;
  cog_x_mm?: number;
  cog_y_mm?: number;
  cog_z_mm?: number;
  cog_ok?: boolean;
  door_axis?: string;
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
