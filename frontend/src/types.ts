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
  /** 已装体积 / 整柜内容积 */
  container_volume_utilization?: number;
  /** 已装重量 / 柜限重 */
  container_weight_utilization?: number | null;
  remaining_volume_m3?: number;
  remaining_weight_kg?: number | null;
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

export type Bottleneck = "volume" | "height" | "weight";

export interface CompareOption {
  code: string;
  length: number;
  width: number;
  height: number;
  max_weight: number;
  fits: boolean;
  container_volume_utilization: number;
  container_weight_utilization?: number | null;
  remaining_volume_m3: number;
  remaining_weight_kg?: number | null;
  bottleneck?: Bottleneck | null;
  bottleneck_label?: string | null;
  detail?: string | null;
  causes: string[];
  short_volume_m3: number;
  short_weight_kg: number;
  short_height_mm: number;
  placed_count: number;
  unplaced_count: number;
}

export interface CompareResponse {
  recommended: string | null;
  options: CompareOption[];
}
